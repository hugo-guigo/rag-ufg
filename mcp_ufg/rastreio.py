"""Rastreio de cada chamada de ferramenta: uma linha JSON no log e, no HTTP, uma linha no banco.

Middleware do servidor MCP (ServerMiddleware do SDK): envolve toda requisição; só as tools/call são
registradas. Campos: id de rastreio, id da requisição JSON-RPC, cliente, ferramenta, argumentos
resumidos, latência, ok ou erro e tamanho da resposta em bytes.

- Id de rastreio: vem do cliente, em _meta ("rastreio") ou no header X-Rastreio; sem nenhum dos dois,
  o servidor cria um. É o que liga o log do cliente ao do servidor para a mesma pergunta.
- Cliente: no HTTP, o client_id do token (o middleware de autenticação o põe no scope da requisição);
  sem HTTP (stdio ou em processo), "local".
- Sem dado sensível: texto livre (a pergunta, o termo) entra só como tamanho. Datas e k entram como são.
"""
import json
import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

import anyio

log = logging.getLogger("mcp_ufg.rastreio")

CHAVE_META = "rastreio"
HEADER = "x-rastreio"
CHAVE_CLIENTE = "cliente_mcp"  # no scope ASGI, preenchida pela autenticação


def resumir(argumentos: dict[str, Any]) -> dict[str, Any]:
    resumo: dict[str, Any] = {}
    for nome, valor in (argumentos or {}).items():
        if isinstance(valor, str) and nome not in ("data_inicio", "data_fim"):
            resumo[f"{nome}_chars"] = len(valor)
        else:
            resumo[nome] = valor
    return resumo


def _id_rastreio(params: dict, request) -> str:
    meta = params.get("_meta") or {}
    valor = meta.get(CHAVE_META) if isinstance(meta, dict) else None
    if not valor and request is not None:
        valor = request.headers.get(HEADER)
    valor = str(valor or uuid.uuid4().hex)
    return valor[:64]


def _cliente(request) -> str:
    if request is None:
        return "local"
    return str(request.scope.get(CHAVE_CLIENTE) or "anonimo")


def _erro_e_tamanho(resultado: Any) -> tuple[bool, int]:
    if resultado is None:
        return False, 0
    if hasattr(resultado, "model_dump_json"):
        texto = resultado.model_dump_json(by_alias=True, exclude_none=True)
        return bool(getattr(resultado, "is_error", False)), len(texto.encode())
    texto = json.dumps(resultado, ensure_ascii=False, default=str)
    return bool(resultado.get("isError")), len(texto.encode())


class Rastreio:
    """`gravar(registro)` é opcional (no HTTP grava no banco); falha ao gravar não derruba a chamada."""

    def __init__(self, gravar: Callable[[dict], None] | None = None, relogio: Callable[[], float] = time.perf_counter):
        self.gravar, self.relogio = gravar, relogio

    async def __call__(self, ctx, call_next):
        if ctx.method != "tools/call":
            return await call_next(ctx)
        params = dict(ctx.params or {})
        request = getattr(ctx, "request", None)
        registro = {
            "evento": "mcp.ferramenta",
            "rastreio": _id_rastreio(params, request),
            "requisicao": str(ctx.request_id),
            "cliente": _cliente(request),
            "ferramenta": str(params.get("name") or ""),
            "argumentos": resumir(params.get("arguments") or {}),
        }
        inicio = self.relogio()
        try:
            resultado = await call_next(ctx)
        except Exception as erro:
            registro |= {"ok": False, "erro": type(erro).__name__, "bytes": 0}
            raise
        else:
            erro, tamanho = _erro_e_tamanho(resultado)
            registro |= {"ok": not erro, "erro": "erro_da_ferramenta" if erro else None, "bytes": tamanho}
            return resultado
        finally:
            registro["ms"] = round(1000 * (self.relogio() - inicio), 1)
            log.info(json.dumps(registro, ensure_ascii=False))
            if self.gravar:
                try:
                    await anyio.to_thread.run_sync(self.gravar, registro)
                except Exception:
                    log.exception("falha ao gravar o rastreio da chamada")
