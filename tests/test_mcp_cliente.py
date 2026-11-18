"""Cliente MCP: backoff exponencial, o que repete e o que não repete, fluxo com o LLM e o rastreio ligado
ao servidor. LLM falso (roteiro de respostas), sem gastar cota do Groq."""
import json
from types import SimpleNamespace

import anyio
import httpx2
import pytest
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client
from mcp.shared.exceptions import MCPError
from mcp.types import INTERNAL_ERROR

from mcp_ufg.cliente import ClienteAssistente, Etapas, PoliticaRetry, com_retry, transitorio
from mcp_ufg.rastreio import Rastreio
from mcp_ufg.servidor import criar_servidor
from tests.mcp_falso import AcervoFalso
from tests.test_mcp_http import RegistroMCPFalso, api_no_ar


def chamada(id_: str, nome: str, argumentos: dict) -> dict:
    return {"id": id_, "type": "function", "function": {"name": nome, "arguments": json.dumps(argumentos)}}


class LLMFalso:
    """Devolve as respostas do roteiro em ordem e guarda o que recebeu."""

    def __init__(self, *roteiro: list[dict]):
        self.roteiro = list(roteiro)
        self.recebido: list[dict] = []

    def ferramentas(self, modelo, mensagens, ferramentas, escolha, max_tokens):
        self.recebido.append({"ferramentas": ferramentas, "escolha": escolha, "mensagens": list(mensagens)})
        return SimpleNamespace(conteudo={"content": "", "tool_calls": self.roteiro.pop(0)},
                               tokens_entrada=1000, tokens_saida=50, ms_total=300.0)


ROTEIRO_TRANCAR = (
    [chamada("c1", "buscar_regulamento", {"pergunta": "quantas vezes posso trancar o curso", "k": 2})],
    [chamada("c2", "responder", {"cobertura": "total", "resposta": "Até duas vezes (Art. 82).",
                                 "citacoes": ["T1", "T9"]})],
)


async def sem_espera(_segundos):
    return None


# ---- backoff e classificação dos erros

def test_limite_das_esperas_dobra_ate_o_teto():
    p = PoliticaRetry(base=0.5, teto=4.0)
    assert [p.limite(n) for n in range(6)] == [0.5, 1.0, 2.0, 4.0, 4.0, 4.0]


@pytest.mark.parametrize("erro, esperado", [
    (MCPError(-32003, "banco fora", {"http_status": 503}), (True, None)),
    (MCPError(-32002, "limite", {"http_status": 429, "retry_after": 60}), (True, 60)),
    (MCPError(-32001, "token inválido", {"http_status": 401}), (False, None)),
    (MCPError(INTERNAL_ERROR, "Server returned an error response"), (True, None)),  # 5xx do proxy, sem JSON-RPC
    (MCPError(-32602, "argumento inválido"), (False, None)),
    (httpx2.ConnectError("recusada"), (True, None)),
    (ExceptionGroup("grupo", [httpx2.ReadTimeout("lento")]), (True, None)),
    (ValueError("bug"), (False, None)),
])
def test_o_que_e_transitorio(erro, esperado):
    assert transitorio(erro) == esperado


def _executar_retry(falhas: list[Exception], politica=PoliticaRetry(base=0.5, teto=8.0)):
    esperas, reconexoes, tentativas = [], [], []

    async def operacao():
        tentativas.append(1)
        if falhas:
            raise falhas.pop(0)
        return "ok"

    async def dormir(s):
        esperas.append(s)

    async def reconectar():
        reconexoes.append(1)

    etapas = Etapas("r")
    resultado = anyio.run(lambda: com_retry(operacao, "op", politica, etapas, dormir, lambda a, b: b, reconectar))
    return resultado, esperas, len(reconexoes), len(tentativas), etapas


def test_duas_falhas_transitorias_esperam_com_backoff_e_reconectam():
    falhas = [httpx2.ConnectError("x"), MCPError(-32003, "fora", {"http_status": 503})]
    resultado, esperas, reconexoes, tentativas, etapas = _executar_retry(falhas)
    assert resultado == "ok" and tentativas == 3
    assert esperas == [0.5, 1.0]  # com o sorteio no limite superior: base, depois o dobro
    assert reconexoes == 2
    assert [e["etapa"] for e in etapas.linhas] == ["retry", "retry"]


def test_erro_permanente_nao_repete():
    with pytest.raises(MCPError):
        _executar_retry([MCPError(-32001, "token inválido", {"http_status": 401})])


def test_esgota_as_tentativas_e_levanta():
    falhas = [httpx2.ConnectError("x")] * 10
    with pytest.raises(httpx2.ConnectError):
        _executar_retry(falhas, PoliticaRetry(tentativas=3))
    assert len(falhas) == 7  # 3 tentativas, nenhuma a mais


def test_retry_after_do_servidor_e_respeitado_e_um_longo_demais_desiste():
    _, esperas, *_ = _executar_retry([MCPError(-32002, "limite", {"http_status": 429, "retry_after": 3})])
    assert esperas == [3.0]  # maior que o backoff (0,5 s)
    with pytest.raises(MCPError):
        _executar_retry([MCPError(-32002, "limite", {"http_status": 429, "retry_after": 60})])


# ---- fluxo completo, com o servidor no mesmo processo

def test_pergunta_ferramenta_resposta_citando_e_o_mesmo_rastreio_no_servidor():
    gravados: list[dict] = []
    servidor = criar_servidor(AcervoFalso(), middleware=[Rastreio(gravados.append)])
    llm = LLMFalso(*ROTEIRO_TRANCAR)
    cliente = ClienteAssistente(lambda: servidor, llm)
    r = anyio.run(cliente.perguntar, "Quantas vezes posso trancar o curso?")

    assert r.resposta == "Até duas vezes (Art. 82)." and r.cobertura == "total"
    assert [(rot, fonte) for rot, fonte, _ in r.citados] == [("T1", "RGCG, Art. 82, p. 25")]
    assert r.citacoes_invalidas == 1  # T9 não foi entregue ao modelo
    assert r.chamadas == [{"ferramenta": "buscar_regulamento", "ok": True,
                           "argumentos": {"pergunta": "quantas vezes posso trancar o curso", "k": 2}}]
    # As ferramentas do LLM são as que o servidor anunciou, mais a responder do cliente.
    definicoes = llm.recebido[0]["ferramentas"]
    assert [d["function"]["name"] for d in definicoes] == ["buscar_regulamento", "consultar_calendario", "responder"]
    assert definicoes[0]["function"]["parameters"]["properties"]["k"]["maximum"] == 10
    # O resultado chegou ao modelo rotulado.
    assert llm.recebido[1]["mensagens"][-1]["content"].startswith("T1 (RGCG, Art. 82, p. 25)")
    # Um id liga o log do cliente ao do servidor.
    assert [g["rastreio"] for g in gravados] == [r.rastreio]
    assert {e["rastreio"] for e in r.etapas} == {r.rastreio}
    assert [e["etapa"] for e in r.etapas] == ["inicio", "conexao", "ferramentas", "llm", "ferramenta", "llm", "resposta"]


def test_erro_da_ferramenta_volta_para_o_modelo_sem_retry():
    llm = LLMFalso(
        [chamada("c1", "consultar_calendario", {"termo": "aulas", "data_inicio": "2026-09-01", "data_fim": "2026-08-01"})],
        [chamada("c2", "responder", {"cobertura": "nenhuma", "resposta": "Não achei.", "citacoes": []})],
    )
    r = anyio.run(ClienteAssistente(lambda: criar_servidor(AcervoFalso()), llm).perguntar, "aulas?")
    assert "data_fim é anterior a data_inicio" in llm.recebido[1]["mensagens"][-1]["content"]
    assert r.chamadas[0]["ok"] is False
    assert not [e for e in r.etapas if e["etapa"] == "retry"]


# ---- pela rede, com falha transitória do servidor e com token inválido

def _http(url: str, token: str):
    return lambda: streamable_http_client(f"{url}/mcp", http_client=create_mcp_http_client(
        headers={"Authorization": f"Bearer {token}"}))


class RegistroQueFalhaAntes(RegistroMCPFalso):
    """O banco cai nas primeiras n conferências de token: o middleware responde 503."""

    def __init__(self, falhas: int):
        super().__init__()
        self.falhas = falhas

    def cliente_do_token(self, token):
        if self.falhas:
            self.falhas -= 1
            raise ConnectionError("banco fora do ar")
        return super().cliente_do_token(token)


def test_503_do_servidor_reconecta_com_backoff_e_responde():
    # Cada tentativa de conexão faz duas requisições (o SDK tenta o handshake novo e depois o antigo),
    # então 4 falhas do banco são 2 conexões perdidas.
    with api_no_ar(RegistroQueFalhaAntes(falhas=4)) as (url, registro):
        cliente = ClienteAssistente(_http(url, "token-bom"), LLMFalso(*ROTEIRO_TRANCAR), dormir=sem_espera)
        r = anyio.run(cliente.perguntar, "Quantas vezes posso trancar o curso?")
    retries = [e for e in r.etapas if e["etapa"] == "retry"]
    assert [e["operacao"] for e in retries] == ["listar_ferramentas", "listar_ferramentas"]
    assert all(e["espera_s"] >= 5 for e in retries)  # o Retry-After do 503 vale mais que o backoff curto
    assert r.citados and r.citados[0][0] == "T1"
    assert registro.gravados[0]["cliente"] == "cliente-a"


def test_token_invalido_falha_na_hora_sem_retry():
    with api_no_ar() as (url, _):
        cliente = ClienteAssistente(_http(url, "token-errado"), LLMFalso(), dormir=sem_espera)
        with pytest.raises(Exception) as info:
            anyio.run(cliente.perguntar, "posso trancar?")
    from mcp_ufg.cliente import folha
    assert isinstance(folha(info.value), MCPError) and folha(info.value).code == -32001
