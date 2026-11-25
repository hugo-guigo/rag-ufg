"""Cliente MCP: conecta ao servidor, descobre as ferramentas e responde a pergunta com o LLM, citando as fontes.

Fluxo de uma pergunta (todas as etapas no log com o mesmo id de rastreio, que também vai para o servidor):
1. conecta (stdio, HTTP com token ou, nos testes, o servidor no mesmo processo) e lista as ferramentas;
2. converte o que o servidor anunciou (nome, descrição, inputSchema) em ferramentas do LLM e acrescenta
   a "responder", que é do cliente;
3. laço com o LLM (gpt-oss-20b no Groq): cada chamada de ferramenta vai ao servidor; o resultado volta
   rotulado (T1, E1...) para o modelo citar;
4. termina na "responder"; citação de rótulo que o modelo não recebeu é descartada.

Por que um laço próprio, e não o Agente de rag/agente.py: o agente executa as ferramentas no processo,
com um schema fixo; o cliente executa no servidor as ferramentas que descobriu. O que é igual vem do
agente: o prompt de sistema, a ferramenta responder e a validação da resposta final.

Retry com backoff exponencial (só nas operações com o servidor MCP, que são todas de leitura):
espera = sorteio uniforme entre 0 e min(teto, base * 2^n), o "full jitter". O sorteio espalha as
tentativas de clientes que falharam juntos (todos voltariam no mesmo instante sem ele). Só repete erro
transitório: conexão, timeout, 429, 502, 503, 504. 401 e erro de argumento não repetem. Com Retry-After
do servidor, espera pelo menos isso; se for mais que max_retry_after, desiste na hora em vez de segurar
a pergunta. O LLM tem o retry próprio do ClienteGroq (espera fixa em 5xx e o retry-after do Groq em 429).
"""
import json
import logging
import random
import time
import uuid
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import anyio
import httpx2
from mcp import Client
from mcp.shared.exceptions import MCPError
from mcp.types import INTERNAL_ERROR

from rag.agente import FERRAMENTAS, FORCAR_RESPOSTA, MAX_PASSOS, SISTEMA, ErroFerramenta, validar_final
from rag.resposta import MODELO_RESPOSTA

log = logging.getLogger("mcp_ufg.cliente")

RESPONDER = next(f for f in FERRAMENTAS if f["function"]["name"] == "responder")
STATUS_TRANSITORIOS = {429, 502, 503, 504}
PREFIXOS = {"trechos": ("T", "texto"), "eventos": ("E", "descricao")}


@dataclass(frozen=True)
class PoliticaRetry:
    tentativas: int = 4  # contando a primeira
    base: float = 0.5  # segundos
    teto: float = 8.0  # maior espera entre duas tentativas
    max_retry_after: float = 15.0  # Retry-After maior que isto: desiste em vez de esperar

    def limite(self, n: int) -> float:
        """Limite superior da n-ésima espera (n = 0 é a espera depois da primeira falha)."""
        return min(self.teto, self.base * 2 ** n)


def folha(erro: BaseException) -> BaseException:
    """O SDK entrega erros de conexão dentro de ExceptionGroup (do TaskGroup); a causa é a primeira folha."""
    while isinstance(erro, BaseExceptionGroup) and erro.exceptions:
        erro = erro.exceptions[0]
    return erro


def transitorio(erro: BaseException) -> tuple[bool, float | None]:
    """(pode repetir?, Retry-After do servidor em segundos, se veio)."""
    erro = folha(erro)
    if isinstance(erro, MCPError):
        dados = erro.data if isinstance(erro.data, dict) else {}
        if dados.get("http_status") in STATUS_TRANSITORIOS:
            return True, dados.get("retry_after")
        # 5xx sem corpo JSON-RPC (ex.: o proxy da nuvem enquanto o container sobe) chega com esta mensagem.
        return erro.code == INTERNAL_ERROR and erro.message == "Server returned an error response", None
    return isinstance(erro, (httpx2.TransportError, TimeoutError, ConnectionError)), None


class ErroCliente(Exception):
    pass


@dataclass
class Etapas:
    """Log do cliente: uma linha JSON por etapa, todas com o mesmo id de rastreio."""

    rastreio: str
    linhas: list[dict] = field(default_factory=list)

    def registrar(self, etapa: str, **campos) -> None:
        linha = {"evento": "mcp.cliente", "rastreio": self.rastreio, "etapa": etapa, **campos}
        self.linhas.append(linha)
        log.info(json.dumps(linha, ensure_ascii=False, default=str))


async def com_retry(operacao: Callable[[], Awaitable[Any]], nome: str, politica: PoliticaRetry, etapas: Etapas,
                    dormir: Callable[[float], Awaitable[None]] = anyio.sleep,
                    sorteio: Callable[[float, float], float] = random.uniform,
                    ao_falhar: Callable[[], Awaitable[None]] | None = None) -> Any:
    for n in range(politica.tentativas):
        try:
            return await operacao()
        except Exception as erro:
            pode, retry_after = transitorio(erro)
            ultima = n == politica.tentativas - 1
            if not pode or ultima:
                etapas.registrar("falha", operacao=nome, tentativa=n + 1, transitorio=pode,
                                 erro=type(folha(erro)).__name__)
                raise
            espera = sorteio(0, politica.limite(n))
            if retry_after is not None:
                if retry_after > politica.max_retry_after:
                    etapas.registrar("falha", operacao=nome, tentativa=n + 1, retry_after=retry_after,
                                     erro="retry_after_longo")
                    raise
                espera = max(espera, float(retry_after))
            etapas.registrar("retry", operacao=nome, tentativa=n + 1, espera_s=round(espera, 3),
                             erro=type(folha(erro)).__name__)
            if ao_falhar:
                await ao_falhar()
            await dormir(espera)
    raise AssertionError("inalcançável")


class SessaoMCP:
    """Uma conexão MCP por pergunta. Falhou de forma transitória: fecha, reconecta e repete."""

    def __init__(self, servidor: Callable[[], Any], politica: PoliticaRetry, etapas: Etapas,
                 dormir=anyio.sleep, sorteio=random.uniform):
        self.servidor, self.politica, self.etapas = servidor, politica, etapas
        self.dormir, self.sorteio = dormir, sorteio
        self.pilha: AsyncExitStack | None = None
        self.cliente: Client | None = None

    async def _abrir(self) -> Client:
        if self.cliente is None:
            inicio = time.perf_counter()
            pilha = AsyncExitStack()
            try:
                self.cliente = await pilha.enter_async_context(Client(self.servidor()))
            except BaseException:
                await pilha.aclose()
                raise
            self.pilha = pilha
            self.etapas.registrar("conexao", ms=round(1000 * (time.perf_counter() - inicio), 1))
        return self.cliente

    async def fechar(self) -> None:
        pilha, self.pilha, self.cliente = self.pilha, None, None
        if pilha:
            try:
                await pilha.aclose()
            except Exception:  # a conexão já estava quebrada; o que importa é abrir outra
                pass

    async def _retry(self, nome: str, operacao):
        return await com_retry(operacao, nome, self.politica, self.etapas, self.dormir, self.sorteio, self.fechar)

    async def listar_ferramentas(self):
        async def op():
            return (await (await self._abrir()).list_tools()).tools
        return await self._retry("listar_ferramentas", op)

    async def chamar(self, nome: str, argumentos: dict):
        async def op():
            cliente = await self._abrir()
            return await cliente.call_tool(nome, argumentos, meta={"rastreio": self.etapas.rastreio})
        return await self._retry(f"ferramenta:{nome}", op)


def para_llm(ferramenta) -> dict:
    """Ferramenta anunciada pelo servidor no formato de tool calling da API do Groq (o da OpenAI)."""
    return {"type": "function", "function": {
        "name": ferramenta.name, "description": ferramenta.description or "", "parameters": ferramenta.input_schema}}


@dataclass
class RespostaCliente:
    pergunta: str
    rastreio: str
    cobertura: str
    resposta: str
    citados: list[tuple[str, str, str]]  # (rótulo curto, fonte, texto)
    ferramentas_anunciadas: list[str]
    chamadas: list[dict]  # ferramenta, argumentos, ok
    chamadas_llm: int
    citacoes_invalidas: int
    tokens_entrada: int
    tokens_saida: int
    ms_total: float
    etapas: list[dict] = field(repr=False, default_factory=list)


class ClienteAssistente:
    def __init__(self, servidor: Callable[[], Any], llm, modelo: str = MODELO_RESPOSTA,
                 politica: PoliticaRetry = PoliticaRetry(), max_passos: int = MAX_PASSOS, hoje: date | None = None,
                 dormir=anyio.sleep, sorteio=random.uniform):
        """servidor: devolve, a cada conexão, o que o Client do SDK aceita (URL com transporte HTTP,
        StdioServerParameters ou uma instância de MCPServer). llm: algo com ferramentas(...) como ClienteGroq."""
        self.servidor, self.llm, self.modelo, self.politica = servidor, llm, modelo, politica
        self.max_passos, self.hoje = max_passos, hoje or date.today()
        self.dormir, self.sorteio = dormir, sorteio

    async def perguntar(self, pergunta: str, rastreio: str | None = None) -> RespostaCliente:
        etapas = Etapas(rastreio or uuid.uuid4().hex)
        inicio = time.perf_counter()
        etapas.registrar("inicio", pergunta_chars=len(pergunta))
        sessao = SessaoMCP(self.servidor, self.politica, etapas, self.dormir, self.sorteio)
        try:
            anunciadas = await sessao.listar_ferramentas()
            etapas.registrar("ferramentas", nomes=[t.name for t in anunciadas])
            resultado = await self._conversar(pergunta, sessao, anunciadas, etapas)
        finally:
            await sessao.fechar()
        resultado.ms_total = round(1000 * (time.perf_counter() - inicio), 1)
        resultado.etapas = etapas.linhas
        etapas.registrar("resposta", cobertura=resultado.cobertura, citacoes=len(resultado.citados),
                         citacoes_invalidas=resultado.citacoes_invalidas, chamadas_llm=resultado.chamadas_llm,
                         ms_total=resultado.ms_total)
        return resultado

    async def _conversar(self, pergunta: str, sessao: SessaoMCP, anunciadas, etapas: Etapas) -> RespostaCliente:
        definicoes = [para_llm(t) for t in anunciadas] + [RESPONDER]
        mensagens = [{"role": "system", "content": SISTEMA.format(hoje=self.hoje.isoformat())},
                     {"role": "user", "content": pergunta}]
        rotulados: dict[str, tuple[str, str, str]] = {}  # T1 -> (id, fonte, texto)
        chamadas: list[dict] = []
        final = None
        chamadas_llm = tokens_entrada = tokens_saida = 0

        for passo in range(1, self.max_passos + 1):
            escolha = FORCAR_RESPOSTA if passo == self.max_passos else "required"
            r = await anyio.to_thread.run_sync(
                lambda: self.llm.ferramentas(self.modelo, mensagens, definicoes, escolha, max_tokens=800))
            chamadas_llm += 1
            tokens_entrada += r.tokens_entrada
            tokens_saida += r.tokens_saida
            pedidos = r.conteudo.get("tool_calls") or []
            etapas.registrar("llm", passo=passo, ms=round(r.ms_total, 1), tokens_entrada=r.tokens_entrada,
                             tokens_saida=r.tokens_saida, ferramentas=[p["function"]["name"] for p in pedidos])
            if not pedidos:
                mensagens.append({"role": "assistant", "content": r.conteudo.get("content") or ""})
                mensagens.append({"role": "user", "content": "Use as ferramentas e termine chamando responder."})
                continue
            mensagens.append({"role": "assistant", "content": r.conteudo.get("content") or "", "tool_calls": pedidos})
            for pedido in pedidos:
                conteudo = await self._executar(pedido, sessao, rotulados, chamadas, etapas)
                if pedido["function"]["name"] == "responder" and isinstance(conteudo, dict):
                    final, conteudo = conteudo, "ok"
                mensagens.append({"role": "tool", "tool_call_id": pedido["id"], "content": conteudo})
            if final is not None:
                break

        if final is None:
            final = {"cobertura": "nenhuma", "citacoes": [],
                     "resposta": "Não consegui concluir a consulta às fontes. Tente reformular a pergunta."}
        citados, invalidas = [], 0
        for rot in dict.fromkeys(c.strip().upper() for c in final["citacoes"]):
            if rot in rotulados:
                _, fonte, texto = rotulados[rot]
                citados.append((rot, fonte, texto))
            else:
                invalidas += 1
        if final["cobertura"] == "nenhuma":
            citados = []
        return RespostaCliente(pergunta, etapas.rastreio, final["cobertura"], final["resposta"].strip(), citados,
                               [t.name for t in anunciadas], chamadas, chamadas_llm, invalidas, tokens_entrada,
                               tokens_saida, 0.0)

    async def _executar(self, pedido: dict, sessao: SessaoMCP, rotulados: dict, chamadas: list,
                        etapas: Etapas) -> str | dict:
        nome = pedido["function"]["name"]
        try:
            argumentos = json.loads(pedido["function"].get("arguments") or "{}")
            if not isinstance(argumentos, dict):
                raise ErroFerramenta("os argumentos devem ser um objeto JSON")
        except (json.JSONDecodeError, ErroFerramenta):
            return "ERRO: argumentos não são um objeto JSON válido"
        if nome == "responder":
            try:
                return validar_final(argumentos)
            except ErroFerramenta as erro:
                return f"ERRO: {erro}"
        inicio = time.perf_counter()
        try:
            resultado = await sessao.chamar(nome, argumentos)
        except Exception as erro:  # esgotou o retry ou erro permanente: o modelo fica sabendo e segue
            etapas.registrar("ferramenta", nome=nome, ok=False, erro=type(folha(erro)).__name__,
                             ms=round(1000 * (time.perf_counter() - inicio), 1))
            chamadas.append({"ferramenta": nome, "argumentos": argumentos, "ok": False})
            return "ERRO: o servidor de ferramentas não respondeu; responda com o que já tem ou diga que não sabe."
        ok = not resultado.is_error
        etapas.registrar("ferramenta", nome=nome, ok=ok, ms=round(1000 * (time.perf_counter() - inicio), 1))
        chamadas.append({"ferramenta": nome, "argumentos": argumentos, "ok": ok})
        if not ok:
            return "ERRO: " + " ".join(c.text for c in resultado.content if getattr(c, "text", None))
        return formatar(resultado.structured_content or {}, rotulados)


def formatar(conteudo: dict, rotulados: dict[str, tuple[str, str, str]]) -> str:
    """Itens do resultado estruturado rotulados para o modelo citar. O mesmo item mantém o rótulo."""
    linhas = []
    for campo, (prefixo, campo_texto) in PREFIXOS.items():
        for item in conteudo.get(campo) or []:
            chave = f"{campo}:{item.get('id')}"
            rot = next((r for r, (k, _, _) in rotulados.items() if k == chave), None)
            if rot is None:
                rot = f"{prefixo}{sum(1 for r in rotulados if r.startswith(prefixo)) + 1}"
                rotulados[rot] = (chave, item.get("rotulo", ""), item.get(campo_texto, ""))
            linhas.append(f"{rot} ({item.get('rotulo', '')})\n{item.get(campo_texto, '')}")
    if not linhas:
        return "Nenhum resultado." if any(campo in conteudo for campo in PREFIXOS) else json.dumps(conteudo, ensure_ascii=False)
    return "\n\n".join(linhas)


__all__ = ["ClienteAssistente", "PoliticaRetry", "RespostaCliente", "com_retry", "transitorio"]
