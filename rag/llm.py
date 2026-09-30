"""Cliente mínimo da API do Groq (compatível com a da OpenAI) com saída JSON presa a um schema.

Três cuidados:
- Ritmo: o plano grátis limita tokens por minuto (TPM) por modelo. O cliente guarda quantos tokens
  gastou nos últimos 60 s e espera antes de passar do limite, em vez de bater no 429.
- 429 mesmo assim: respeita o cabeçalho retry-after (segundos) e tenta de novo.
- Erro de rede ou 5xx: tenta de novo poucas vezes, com espera fixa. Erro 4xx de outro tipo não repete.
Serve para as duas formas de chamada: saída JSON presa a um schema (json) e tool calling (ferramentas).
Na API (etapa 6), max_espera limita quanto uma chamada pode esperar somando todas as esperas; passando
disso, ErroOcupado, e a API responde 503 com Retry-After em vez de segurar a requisição por um minuto.
"""
import json
import os
import re
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

import httpx

URL = "https://api.groq.com/openai/v1/chat/completions"
TPM_PLANO_GRATIS = 8000
MAX_ESPERAS_429 = 10
# O gpt-oss escreve no formato Harmony, em que o nome da ferramenta vem seguido do canal
# ("responder<|channel|>commentary"). Às vezes o sufixo vaza para o nome, e o Groq recusa a chamada
# com 400 tool_use_failed. Na avaliação da etapa 5 isso aconteceu sempre na mesma pergunta (s01), com
# argumentos perfeitos: repetir não adianta.
RE_SUFIXO_HARMONY = re.compile(r"<\|[a-z_]+\|>.*$")


class ErroLLM(Exception):
    pass


class ErroOcupado(ErroLLM):
    """O limite por minuto do plano grátis exigiria esperar mais que max_espera."""

    def __init__(self, segundos: float):
        super().__init__(f"limite de uso do Groq: tente de novo em {segundos:.0f} s")
        self.segundos = segundos


@dataclass(frozen=True)
class RespostaLLM:
    conteudo: dict
    modelo: str
    tokens_entrada: int
    tokens_saida: int
    ms: float  # só a requisição que deu certo
    ms_total: float  # inclui esperas de ritmo e de retry
    tentativas: int


class ClienteGroq:
    def __init__(self, chave: str | None = None, tpm: int = TPM_PLANO_GRATIS, timeout: float = 30.0,
                 transporte: httpx.BaseTransport | None = None,
                 dormir: Callable[[float], None] = time.sleep, relogio: Callable[[], float] = time.monotonic,
                 max_espera: float | None = None):
        chave = chave or os.environ.get("GROQ_API_KEY", "")
        if not chave:
            raise ErroLLM("GROQ_API_KEY vazia: coloque a chave no .env")
        self.http = httpx.Client(headers={"Authorization": f"Bearer {chave}"}, timeout=timeout, transport=transporte)
        self.tpm = tpm
        self.dormir, self.relogio = dormir, relogio
        self.gastos: dict[str, deque[tuple[float, int]]] = {}  # modelo -> (instante, tokens)
        self.limites_dobrados = 0
        self.chamadas_quebradas = 0
        self.chamadas_consertadas = 0
        self.max_espera = max_espera
        self.trava = threading.Lock()  # a API atende várias requisições em threads

    def _dormir(self, segundos: float, esperado: float) -> float:
        """Espera e devolve o total esperado na chamada. Com max_espera, desiste antes de passar dele."""
        if self.max_espera is not None and esperado + segundos > self.max_espera:
            raise ErroOcupado(segundos)
        self.dormir(segundos)
        return esperado + segundos

    def _esperar_vez(self, modelo: str, estimativa: int, esperado: float = 0.0) -> float:
        while True:
            with self.trava:
                gastos = self.gastos.setdefault(modelo, deque())
                agora = self.relogio()
                while gastos and agora - gastos[0][0] >= 60:
                    gastos.popleft()
                if not gastos or sum(t for _, t in gastos) + estimativa <= self.tpm:
                    return esperado
                espera = 60 - (agora - gastos[0][0]) + 0.1
            esperado = self._dormir(espera, esperado)

    def _registrar_gasto(self, modelo: str, tokens: int) -> None:
        with self.trava:
            self.gastos.setdefault(modelo, deque()).append((self.relogio(), tokens))

    def _enviar(self, corpo: dict, estimativa_tokens: int, max_tentativas: int) -> tuple[dict, float, float, int]:
        """Faz a requisição com as regras de ritmo e de retry. Devolve (json, ms, ms_total, tentativas).

        Esperas por 429 não gastam tentativas: o limite por minuto sempre libera, e o Groq às vezes
        pede esperas de 1 ou 2 s, que acabariam com 5 tentativas antes de a janela de 60 s passar.
        """
        modelo = corpo["model"]
        if modelo.startswith("openai/gpt-oss"):
            corpo |= {"reasoning_effort": "low", "include_reasoning": False}
        inicio = self.relogio()
        dobrou = False
        chamada_quebrada = esperas_429 = 0
        tentativa = 0
        esperado = 0.0
        while tentativa < max_tentativas:
            tentativa += 1
            esperado = self._esperar_vez(modelo, estimativa_tokens, esperado)
            t0 = self.relogio()
            try:
                r = self.http.post(URL, json=corpo)
            except httpx.TransportError as erro:  # timeout, conexão recusada
                if tentativa == max_tentativas:
                    raise ErroLLM(f"rede: {erro}") from erro
                esperado = self._dormir(2, esperado)
                continue
            if r.status_code == 429:
                if esperas_429 == MAX_ESPERAS_429:
                    break
                esperas_429 += 1
                tentativa -= 1
                pedido = float(r.headers.get("retry-after", 10))
                if self.max_espera is not None and esperado + pedido > self.max_espera:
                    # O tempo real, sem o teto de 60 s: no limite diário (TPD) o Groq pede minutos.
                    raise ErroOcupado(pedido)
                esperado = self._dormir(min(pedido, 60), esperado)
                continue
            if r.status_code >= 500 and tentativa < max_tentativas:
                esperado = self._dormir(2, esperado)
                continue
            if (r.status_code == 400 and "max completion tokens" in r.text and not dobrou
                    and tentativa < max_tentativas):
                # Com schema strict, JSON cortado vira erro 400. Aconteceu 1 vez em ~60 chamadas na
                # avaliação: o modelo gastou o limite antes de fechar o JSON. Uma nova tentativa com o
                # dobro do limite resolve sem abrir mão do schema.
                corpo["max_completion_tokens"] *= 2
                dobrou = True
                self.limites_dobrados += 1
                continue
            if r.status_code == 400 and "tool_use_failed" in r.text:
                consertada = consertar_chamada(r, corpo)
                if consertada is not None:
                    self.chamadas_consertadas += 1
                    self._registrar_gasto(modelo, estimativa_tokens)
                    fim = self.relogio()
                    return consertada, 1000 * (fim - t0), 1000 * (fim - inicio), tentativa
                if chamada_quebrada < 2 and tentativa < max_tentativas:
                    # Chamada de ferramenta que não é JSON válido: repete até 2 vezes.
                    chamada_quebrada += 1
                    self.chamadas_quebradas += 1
                    continue
            if r.status_code != 200:
                raise ErroLLM(f"HTTP {r.status_code}: {r.text[:300]}")
            dados = r.json()
            self._registrar_gasto(modelo, dados.get("usage", {}).get("total_tokens", estimativa_tokens))
            fim = self.relogio()
            return dados, 1000 * (fim - t0), 1000 * (fim - inicio), tentativa
        raise ErroLLM(f"desisti depois de {max_tentativas} tentativas e {esperas_429} esperas por limite de requisições")

    def json(self, modelo: str, mensagens: list[dict], schema: dict, nome: str,
             max_tokens: int = 1024, estimativa_tokens: int = 2000, max_tentativas: int = 5) -> RespostaLLM:
        corpo = {
            "model": modelo,
            "messages": mensagens,
            "temperature": 0,
            "max_completion_tokens": max_tokens,
            "response_format": {"type": "json_schema", "json_schema": {"name": nome, "schema": schema, "strict": True}},
        }
        dados, ms, ms_total, tentativas = self._enviar(corpo, estimativa_tokens, max_tentativas)
        uso = dados.get("usage", {})
        try:
            conteudo = json.loads(dados["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as erro:
            raise ErroLLM(f"resposta fora do formato: {str(dados)[:300]}") from erro
        return RespostaLLM(conteudo, modelo, uso.get("prompt_tokens", 0), uso.get("completion_tokens", 0),
                           ms, ms_total, tentativas)

    def ferramentas(self, modelo: str, mensagens: list[dict], ferramentas: list[dict], escolha: str | dict = "required",
                    max_tokens: int = 1024, estimativa_tokens: int = 3000, max_tentativas: int = 5) -> RespostaLLM:
        """Uma rodada de tool calling. conteudo = a mensagem do assistente (com "tool_calls").

        escolha: "required" obriga a chamar alguma ferramenta; {"type": "function", "function": {"name": ...}}
        obriga a chamar aquela.
        """
        corpo = {
            "model": modelo,
            "messages": mensagens,
            "temperature": 0,
            "max_completion_tokens": max_tokens,
            "tools": ferramentas,
            "tool_choice": escolha,
        }
        dados, ms, ms_total, tentativas = self._enviar(corpo, estimativa_tokens, max_tentativas)
        uso = dados.get("usage", {})
        try:
            mensagem = dados["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as erro:
            raise ErroLLM(f"resposta fora do formato: {str(dados)[:300]}") from erro
        return RespostaLLM(mensagem, modelo, uso.get("prompt_tokens", 0), uso.get("completion_tokens", 0),
                           ms, ms_total, tentativas)


def consertar_chamada(r: httpx.Response, corpo: dict) -> dict | None:
    """Recupera a chamada recusada só no caso do sufixo do Harmony no nome.

    Exige: failed_generation é JSON com "name" e "arguments" (objeto), e o nome sem o sufixo é uma das
    ferramentas oferecidas na requisição. Qualquer outro erro de chamada continua sendo erro. Devolve uma
    resposta no formato normal da API, sem "usage" (o Groq não informa os tokens da chamada recusada).
    """
    try:
        gerado = json.loads(r.json()["error"]["failed_generation"])
    except (KeyError, TypeError, ValueError):
        return None
    if not isinstance(gerado, dict) or not isinstance(gerado.get("arguments"), dict):
        return None
    nome = RE_SUFIXO_HARMONY.sub("", str(gerado.get("name", "")))
    oferecidas = {f["function"]["name"] for f in corpo.get("tools", [])}
    if nome == gerado.get("name") or nome not in oferecidas:
        return None
    chamada = {"id": "consertada-1", "type": "function",
               "function": {"name": nome, "arguments": json.dumps(gerado["arguments"], ensure_ascii=False)}}
    return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [chamada]}}], "usage": {}}
