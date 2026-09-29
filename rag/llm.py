"""Cliente mínimo da API do Groq (compatível com a da OpenAI) com saída JSON presa a um schema.

Três cuidados:
- Ritmo: o plano grátis limita tokens por minuto (TPM) por modelo. O cliente guarda quantos tokens
  gastou nos últimos 60 s e espera antes de passar do limite, em vez de bater no 429.
- 429 mesmo assim: respeita o cabeçalho retry-after (segundos) e tenta de novo.
- Erro de rede ou 5xx: tenta de novo poucas vezes, com espera fixa. Erro 4xx de outro tipo não repete.
"""
import json
import os
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

import httpx

URL = "https://api.groq.com/openai/v1/chat/completions"
TPM_PLANO_GRATIS = 8000


class ErroLLM(Exception):
    pass


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
                 dormir: Callable[[float], None] = time.sleep, relogio: Callable[[], float] = time.monotonic):
        chave = chave or os.environ.get("GROQ_API_KEY", "")
        if not chave:
            raise ErroLLM("GROQ_API_KEY vazia: coloque a chave no .env")
        self.http = httpx.Client(headers={"Authorization": f"Bearer {chave}"}, timeout=timeout, transport=transporte)
        self.tpm = tpm
        self.dormir, self.relogio = dormir, relogio
        self.gastos: dict[str, deque[tuple[float, int]]] = {}  # modelo -> (instante, tokens)
        self.limites_dobrados = 0

    def _esperar_vez(self, modelo: str, estimativa: int) -> None:
        gastos = self.gastos.setdefault(modelo, deque())
        while True:
            agora = self.relogio()
            while gastos and agora - gastos[0][0] >= 60:
                gastos.popleft()
            if not gastos or sum(t for _, t in gastos) + estimativa <= self.tpm:
                return
            self.dormir(60 - (agora - gastos[0][0]) + 0.1)

    def json(self, modelo: str, mensagens: list[dict], schema: dict, nome: str,
             max_tokens: int = 1024, estimativa_tokens: int = 2000, max_tentativas: int = 5) -> RespostaLLM:
        corpo = {
            "model": modelo,
            "messages": mensagens,
            "temperature": 0,
            "max_completion_tokens": max_tokens,
            "response_format": {"type": "json_schema", "json_schema": {"name": nome, "schema": schema, "strict": True}},
        }
        if modelo.startswith("openai/gpt-oss"):
            corpo |= {"reasoning_effort": "low", "include_reasoning": False}
        inicio = self.relogio()
        dobrou = False
        for tentativa in range(1, max_tentativas + 1):
            self._esperar_vez(modelo, estimativa_tokens)
            t0 = self.relogio()
            try:
                r = self.http.post(URL, json=corpo)
            except httpx.TransportError as erro:  # timeout, conexão recusada
                if tentativa == max_tentativas:
                    raise ErroLLM(f"rede: {erro}") from erro
                self.dormir(2)
                continue
            if r.status_code == 429:
                self.dormir(min(float(r.headers.get("retry-after", 10)), 60))
                continue
            if r.status_code >= 500 and tentativa < max_tentativas:
                self.dormir(2)
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
            if r.status_code != 200:
                raise ErroLLM(f"HTTP {r.status_code}: {r.text[:300]}")
            dados = r.json()
            uso = dados.get("usage", {})
            self.gastos[modelo].append((self.relogio(), uso.get("total_tokens", estimativa_tokens)))
            try:
                conteudo = json.loads(dados["choices"][0]["message"]["content"])
            except (KeyError, IndexError, json.JSONDecodeError) as erro:
                raise ErroLLM(f"resposta fora do formato: {str(dados)[:300]}") from erro
            fim = self.relogio()
            return RespostaLLM(conteudo, modelo, uso.get("prompt_tokens", 0), uso.get("completion_tokens", 0),
                               1000 * (fim - t0), 1000 * (fim - inicio), tentativa)
        raise ErroLLM(f"desisti depois de {max_tentativas} tentativas (limite de requisições)")
