"""Transporte Streamable HTTP do MCP, montado na API em /mcp: token Bearer, limite de uso e rastreio no banco.

Por que um middleware próprio para o token, e não o do SDK: o SDK só confere Bearer junto com a URL de
um servidor de autorização OAuth, que ele publica no metadata para os clientes. Aqui não há servidor
de autorização (os tokens são emitidos por scripts/token_mcp.py), e publicar uma URL inexistente faria
clientes tentarem um fluxo OAuth que não existe. Ver docs/specs/mcp.md, decisões 4 e 5.

Ordem em cada requisição HTTP para /mcp:
1. sem "Authorization: Bearer <token>", ou token desconhecido ou revogado: 401 com WWW-Authenticate;
2. cliente acima do limite (contado em chamadas_mcp, vale para todas as instâncias): 429 com Retry-After;
3. o client_id vai para o scope da requisição, onde o rastreio o lê, e a requisição segue para o SDK.
"""
import hashlib
import json
import logging
import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field

import anyio

from mcp_ufg.rastreio import CHAVE_CLIENTE
from rag.registro import Contagem, Limites

log = logging.getLogger("mcp_ufg.http")

REALM = "rag-ufg-mcp"

CONTAGEM = """
    SELECT count(*) FILTER (WHERE cliente = %(c)s AND criado_em > now() - interval '1 minute'),
           count(*) FILTER (WHERE cliente = %(c)s),
           count(*)
    FROM chamadas_mcp
    WHERE criado_em > now() - interval '1 day'"""

CAMPOS = ("rastreio", "requisicao", "cliente", "ferramenta", "argumentos", "ok", "erro", "ms", "bytes")
INSERCAO = f"INSERT INTO chamadas_mcp ({', '.join(CAMPOS)}) VALUES ({', '.join('%(' + c + ')s' for c in CAMPOS)})"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def novo_token() -> str:
    """256 bits aleatórios; o prefixo identifica o tipo de credencial se ela vazar num log."""
    return "ufgmcp_" + secrets.token_urlsafe(32)


def limites_do_ambiente() -> Limites:
    """As ferramentas não gastam cota do Groq (só embedding e banco): limites maiores que os da API."""
    def inteiro(nome: str, padrao: int) -> int:
        return int(os.environ.get(nome) or padrao)
    return Limites(inteiro("MCP_LIMITE_POR_MINUTO", 30), inteiro("MCP_LIMITE_POR_DIA", 500),
                   inteiro("MCP_LIMITE_TOTAL_POR_DIA", 2000))


class RegistroMCP:
    """Tokens, contagem e rastreio na mesma conexão de pool da API."""

    def __init__(self, pool):
        self.pool = pool

    def cliente_do_token(self, token: str) -> str | None:
        with self.pool.connection() as conexao:
            linha = conexao.execute(
                "SELECT id FROM clientes_mcp WHERE token_sha256 = %s AND revogado_em IS NULL",
                (hash_token(token),)).fetchone()
        return linha[0] if linha else None

    def contar(self, cliente: str) -> Contagem:
        with self.pool.connection() as conexao:
            return Contagem(*conexao.execute(CONTAGEM, {"c": cliente}).fetchone())

    def gravar(self, registro: dict) -> None:
        valores = {c: registro.get(c) for c in CAMPOS}
        valores["argumentos"] = json.dumps(valores["argumentos"] or {}, ensure_ascii=False, default=str)
        valores["ms"] = round(valores["ms"] or 0)
        valores["bytes"] = int(valores["bytes"] or 0)
        with self.pool.connection() as conexao:
            conexao.execute(INSERCAO, valores)


async def _responder(send, status: int, corpo: dict, cabecalhos: dict[str, str]) -> None:
    dados = json.dumps(corpo, ensure_ascii=False).encode()
    lista = [(b"content-type", b"application/json"), (b"content-length", str(len(dados)).encode())]
    lista += [(k.lower().encode(), v.encode()) for k, v in cabecalhos.items()]
    await send({"type": "http.response.start", "status": status, "headers": lista})
    await send({"type": "http.response.body", "body": dados})


@dataclass
class ExigirToken:
    """Middleware ASGI na frente do app MCP do SDK."""

    app: Callable
    registro: Callable[[], object]  # devolve o RegistroMCP (montado depois, no início da API)
    limites: Limites = field(default_factory=Limites)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        cabecalho = dict(scope.get("headers") or []).get(b"authorization", b"").decode("latin-1")
        esquema, _, token = cabecalho.partition(" ")
        if esquema.lower() != "bearer" or not token.strip():
            return await _responder(send, 401, {"erro": "envie Authorization: Bearer <token>"},
                                    {"WWW-Authenticate": f'Bearer realm="{REALM}"'})
        registro = self.registro()
        if registro is None:
            return await _responder(send, 503, {"erro": "MCP desligado nesta instância"}, {})
        try:
            cliente = await anyio.to_thread.run_sync(registro.cliente_do_token, token.strip())
            contagem = await anyio.to_thread.run_sync(registro.contar, cliente) if cliente else None
        except Exception:
            log.exception("banco fora do ar ao conferir o token")
            return await _responder(send, 503, {"erro": "banco de dados indisponível; tente mais tarde"},
                                    {"Retry-After": "30"})
        if cliente is None:
            return await _responder(send, 401, {"erro": "token inválido ou revogado"},
                                    {"WWW-Authenticate": f'Bearer realm="{REALM}", error="invalid_token"'})
        bloqueio = contagem.bloqueio(self.limites)
        if bloqueio:
            motivo, segundos = bloqueio
            return await _responder(send, 429, {"erro": f"você atingiu o {motivo} do MCP"},
                                    {"Retry-After": str(segundos)})
        scope[CHAVE_CLIENTE] = cliente
        await self.app(scope, receive, send)


def hosts_permitidos() -> list[str]:
    """Proteção contra DNS rebinding do SDK: Host aceito. Local sempre; o domínio da nuvem vem do ambiente."""
    extras = [h.strip() for h in os.environ.get("MCP_HOSTS", "").split(",") if h.strip()]
    return ["127.0.0.1:*", "localhost:*", "[::1]:*", *extras]


# ---- administração dos tokens (com a conexão de admin; o usuário app só lê clientes_mcp)

def criar_cliente(conexao, cliente: str) -> str:
    """Cria o cliente e devolve o token em claro, que não fica guardado em lugar nenhum."""
    if not cliente.strip() or len(cliente) > 64:
        raise ValueError("o nome do cliente deve ter de 1 a 64 caracteres")
    token = novo_token()
    conexao.execute("INSERT INTO clientes_mcp (id, token_sha256) VALUES (%s, %s)", (cliente.strip(), hash_token(token)))
    return token


def revogar_cliente(conexao, cliente: str) -> bool:
    linha = conexao.execute(
        "UPDATE clientes_mcp SET revogado_em = now() WHERE id = %s AND revogado_em IS NULL RETURNING id",
        (cliente,)).fetchone()
    return linha is not None


def listar_clientes(conexao) -> list[tuple]:
    return conexao.execute("""
        SELECT c.id, c.criado_em, c.revogado_em,
               (SELECT count(*) FROM chamadas_mcp m WHERE m.cliente = c.id AND m.criado_em > now() - interval '1 day')
        FROM clientes_mcp c ORDER BY c.criado_em""").fetchall()
