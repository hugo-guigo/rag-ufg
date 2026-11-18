"""MCP pelo HTTP montado na API (/mcp): token, limite, rastreio com o cliente e proteção de Host.

A API sobe de verdade (uvicorn numa thread, porta livre) com acervo e registro falsos, e o cliente é o
do SDK, pela rede. Sem banco.
"""
import contextlib
import socket
import threading
import time

import anyio
import httpx
import pytest
import uvicorn
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

from api.app import criar_app
from api.servicos import Servicos
from rag.registro import Contagem, Limites
from tests.mcp_falso import AcervoFalso
from tests.test_api import AgenteFalso, RegistroFalso

INITIALIZE = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "teste", "version": "1"}}}
CABECALHOS_MCP = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}


class RegistroMCPFalso:
    def __init__(self, banco_ok: bool = True):
        self.tokens = {"token-bom": "cliente-a"}
        self.gravados: list[dict] = []
        self.ok = banco_ok

    def cliente_do_token(self, token):
        if not self.ok:
            raise ConnectionError("banco fora do ar")
        return self.tokens.get(token)

    def contar(self, cliente):
        meus = sum(1 for g in self.gravados if g["cliente"] == cliente)
        return Contagem(meus, meus, len(self.gravados))

    def gravar(self, registro):
        self.gravados.append(dict(registro))


@contextlib.contextmanager
def api_no_ar(registro_mcp="padrao", limites_mcp: Limites | None = None):
    registro_mcp = RegistroMCPFalso() if registro_mcp == "padrao" else registro_mcp
    servicos = Servicos(AgenteFalso(), RegistroFalso(), "sal", acervo=AcervoFalso(), registro_mcp=registro_mcp)
    app = criar_app(lambda: servicos, limites_mcp)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
    servidor = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=porta, log_level="warning"))
    thread = threading.Thread(target=servidor.run, daemon=True)
    thread.start()
    while not servidor.started:
        time.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{porta}", registro_mcp
    finally:
        servidor.should_exit = True
        thread.join(5)


def post(url: str, token: str | None = None, **cabecalhos) -> httpx.Response:
    h = CABECALHOS_MCP | cabecalhos
    if token:
        h["Authorization"] = f"Bearer {token}"
    return httpx.post(f"{url}/mcp", json=INITIALIZE, headers=h)


def chamar_ferramenta(url: str, token: str, nome: str, argumentos: dict, cabecalhos: dict | None = None):
    async def chamar():
        http = create_mcp_http_client(headers={"Authorization": f"Bearer {token}", **(cabecalhos or {})})
        async with Client(streamable_http_client(f"{url}/mcp", http_client=http)) as cliente:
            return await cliente.call_tool(nome, argumentos)
    return anyio.run(chamar)


def test_sem_token_e_com_token_errado_401():
    with api_no_ar() as (url, _):
        sem = post(url)
        assert sem.status_code == 401
        assert sem.headers["www-authenticate"] == 'Bearer realm="rag-ufg-mcp"'
        errado = post(url, "token-que-nao-existe")
        assert errado.status_code == 401
        assert 'error="invalid_token"' in errado.headers["www-authenticate"]
        basic = httpx.post(f"{url}/mcp", json=INITIALIZE, headers=CABECALHOS_MCP | {"Authorization": "Basic eDp5"})
        assert basic.status_code == 401


def test_token_certo_passa_e_o_rastreio_leva_o_cliente_e_o_id_do_header():
    with api_no_ar() as (url, registro):
        assert post(url, "token-bom").status_code == 200  # /mcp sem barra, sem redirecionar
        r = chamar_ferramenta(url, "token-bom", "buscar_regulamento", {"pergunta": "posso trancar?", "k": 1},
                              {"X-Rastreio": "pergunta-7"})
    assert not r.is_error
    assert r.structured_content["trechos"][0]["id"] == "rgcg-82"
    (gravado,) = registro.gravados
    assert {"cliente": "cliente-a", "rastreio": "pergunta-7", "ferramenta": "buscar_regulamento", "ok": True}.items() \
        <= gravado.items()


def test_limite_por_minuto_responde_429_com_retry_after():
    registro = RegistroMCPFalso()
    registro.gravados = [{"cliente": "cliente-a"}] * 2
    with api_no_ar(registro, Limites(por_minuto=2, por_dia=100, total_por_dia=100)) as (url, _):
        r = post(url, "token-bom")
    assert r.status_code == 429
    assert r.headers["retry-after"] == "60"


def test_banco_fora_do_ar_503_e_mcp_desligado_503():
    with api_no_ar(RegistroMCPFalso(banco_ok=False)) as (url, _):
        assert post(url, "token-bom").status_code == 503
    with api_no_ar(None) as (url, _):
        assert post(url, "token-bom").status_code == 503


def test_host_fora_da_lista_e_recusado(monkeypatch):
    """Proteção contra DNS rebinding do SDK: só os hosts da lista (local e MCP_HOSTS)."""
    with api_no_ar() as (url, _):
        assert post(url, "token-bom", Host="exemplo.com").status_code in (400, 421)
    monkeypatch.setenv("MCP_HOSTS", "exemplo.com")
    with api_no_ar() as (url, _):
        assert post(url, "token-bom", Host="exemplo.com").status_code == 200


def test_rotas_antigas_continuam_iguais():
    with api_no_ar() as (url, _):
        assert httpx.get(f"{url}/health").json() == {"status": "ok", "banco": "ok"}
        assert httpx.post(f"{url}/perguntar", json={"pergunta": "quando começam as aulas?"}).status_code == 200


@pytest.mark.parametrize("caminho", ["/mcp", "/mcp/"])
def test_os_dois_caminhos_funcionam(caminho):
    with api_no_ar() as (url, _):
        r = httpx.post(f"{url}{caminho}", json=INITIALIZE, headers=CABECALHOS_MCP | {"Authorization": "Bearer token-bom"})
    assert r.status_code == 200
    assert r.json()["result"]["serverInfo"]["name"] == "assistente-ufg"
