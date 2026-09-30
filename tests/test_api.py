"""API com agente e registro falsos: testa rotas, limites, erros e o que vai para o log."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from api.app import criar_app, ip_do_cliente
from api.servicos import Servicos
from rag.agente import Passo, RespostaAgente
from rag.busca import Evento
from rag.llm import ErroLLM, ErroOcupado
from rag.registro import Contagem, Limites, hash_cliente

EVENTO = Evento(1, date(2026, 8, 10), date(2026, 8, 10), "Início das aulas de 2026/2 da Graduação", 14)


def resposta_agente(pergunta: str) -> RespostaAgente:
    return RespostaAgente(
        pergunta, "total", "As aulas de 2026/2 começam em 10/08/2026.",
        [("E1", "Calendário 2026, 10/08/2026, p. 14", EVENTO.descricao)],
        [Passo("consultar_calendario", {"termo": "início das aulas 2026/2"}, ["E1"], 12.0),
         Passo("responder", {"cobertura": "total"}, [], 0.1)],
        2, False, 0, 0, 900.0, 900.0, 12.1, 2100, 150, "openai/gpt-oss-20b")


class AgenteFalso:
    def __init__(self, erro: Exception | None = None):
        self.erro, self.perguntas = erro, []

    def perguntar(self, pergunta):
        self.perguntas.append(pergunta)
        if self.erro:
            raise self.erro
        return resposta_agente(pergunta)


class RegistroFalso:
    """Guarda as linhas em memória e conta como o SQL: minuto = últimas N, só status diferente de 429."""

    def __init__(self, banco_ok: bool = True, total_no_dia: int = 0):
        self.linhas: list[dict] = []
        self.ok, self.total_extra = banco_ok, total_no_dia

    def contar(self, cliente):
        if not self.ok:
            raise ConnectionError("banco fora do ar")
        validas = [x for x in self.linhas if x["status"] != 429]
        doc = [x for x in validas if x["cliente"] == cliente]
        return Contagem(len(doc), len(doc), len(validas) + self.total_extra)

    def gravar(self, linha):
        self.linhas.append(dict(linha))
        return len(self.linhas)

    def banco_ok(self):
        return self.ok


def cliente_http(agente=None, registro=None, limites=Limites(), confiar_proxy=False):
    servicos = Servicos(agente or AgenteFalso(), registro or RegistroFalso(), "sal-de-teste", limites, confiar_proxy)
    return TestClient(criar_app(lambda: servicos)), servicos


def test_health_consulta_o_banco():
    with cliente_http()[0] as http:
        assert http.get("/health").json() == {"status": "ok", "banco": "ok"}
    with cliente_http(registro=RegistroFalso(banco_ok=False))[0] as http:
        assert http.get("/health").status_code == 503


def test_pergunta_devolve_resposta_fontes_e_ferramentas_e_grava_o_log():
    http, servicos = cliente_http()
    with http:
        r = http.post("/perguntar", json={"pergunta": "  Quando começa 2026/2?  "})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["resposta"].startswith("As aulas") and corpo["id"] == 1 and corpo["latencia_ms"] >= 0
    assert corpo["fontes"] == [{"rotulo": "E1", "fonte": "Calendário 2026, 10/08/2026, p. 14", "texto": EVENTO.descricao}]
    assert corpo["ferramentas"] == [{"nome": "consultar_calendario", "argumentos": {"termo": "início das aulas 2026/2"},
                                     "erro": None}]
    assert servicos.agente.perguntas == ["Quando começa 2026/2?"]  # espaços das pontas removidos
    linha = servicos.registro.linhas[0]
    assert linha["status"] == 200 and linha["tokens_entrada"] == 2100 and linha["chamadas_llm"] == 2
    assert linha["ferramentas"] == ["consultar_calendario", "responder"] and linha["citacoes"] == 1
    assert linha["cliente"] == hash_cliente("testclient", "sal-de-teste") and "testclient" not in str(linha)


@pytest.mark.parametrize("pergunta", ["", "  a ", "x" * 501])
def test_pergunta_invalida_e_recusada_sem_chamar_o_agente(pergunta):
    http, servicos = cliente_http()
    with http:
        assert http.post("/perguntar", json={"pergunta": pergunta}).status_code == 422
    assert servicos.agente.perguntas == [] and servicos.registro.linhas == []


def test_limite_por_minuto_devolve_429_com_retry_after_e_registra():
    http, servicos = cliente_http(limites=Limites(por_minuto=2, por_dia=10, total_por_dia=100))
    with http:
        codigos = [http.post("/perguntar", json={"pergunta": "qual a nota mínima?"}).status_code for _ in range(3)]
        bloqueada = http.post("/perguntar", json={"pergunta": "qual a nota mínima?"})
    assert codigos == [200, 200, 429]
    assert bloqueada.headers["retry-after"] == "60" and "por minuto" in bloqueada.json()["detail"]
    assert len(servicos.agente.perguntas) == 2
    assert [x["status"] for x in servicos.registro.linhas] == [200, 200, 429, 429]


def test_limite_diario_global_vale_para_todos():
    registro = RegistroFalso(total_no_dia=50)
    with cliente_http(registro=registro)[0] as http:
        r = http.post("/perguntar", json={"pergunta": "qual a nota mínima?"})
    assert r.status_code == 429 and "limite diário" in r.json()["detail"] and r.headers["retry-after"] == "3600"


def test_groq_no_limite_vira_503_com_retry_after():
    http, servicos = cliente_http(agente=AgenteFalso(ErroOcupado(42.3)))
    with http:
        r = http.post("/perguntar", json={"pergunta": "qual a nota mínima?"})
    assert r.status_code == 503 and r.headers["retry-after"] == "42"
    assert servicos.registro.linhas[0]["erro"].startswith("limite de uso do Groq")


def test_erros_do_llm_e_inesperados_nao_vazam_detalhes():
    http, servicos = cliente_http(agente=AgenteFalso(ErroLLM("HTTP 401: chave gsk_xyz inválida")))
    with http:
        r = http.post("/perguntar", json={"pergunta": "qual a nota mínima?"})
    assert r.status_code == 503 and "gsk_" not in r.text
    http, servicos = cliente_http(agente=AgenteFalso(KeyError("segredo")))
    with http:
        r = http.post("/perguntar", json={"pergunta": "qual a nota mínima?"})
    assert r.status_code == 500 and r.json()["detail"] == "Erro interno." and "segredo" not in r.text
    assert servicos.registro.linhas[0]["erro"] == "KeyError: 'segredo'"  # o detalhe fica só no log


def test_banco_fora_do_ar_nao_chama_o_agente():
    http, servicos = cliente_http(registro=RegistroFalso(banco_ok=False))
    with http:
        assert http.post("/perguntar", json={"pergunta": "qual a nota mínima?"}).status_code == 503
    assert servicos.agente.perguntas == []


def test_falha_ao_gravar_o_log_nao_impede_a_resposta():
    class RegistroQueNaoGrava(RegistroFalso):
        def gravar(self, linha):
            raise ConnectionError("caiu no meio")

    with cliente_http(registro=RegistroQueNaoGrava())[0] as http:
        r = http.post("/perguntar", json={"pergunta": "qual a nota mínima?"})
    assert r.status_code == 200 and r.json()["id"] is None


def test_ip_atras_do_proxy_usa_o_ultimo_x_forwarded_for():
    class Req:
        def __init__(self, xff):
            self.headers = {"x-forwarded-for": xff} if xff else {}
            self.client = type("C", (), {"host": "10.0.0.1"})()

    # o cliente pode forjar o começo da lista; o proxy acrescenta o IP real no fim
    assert ip_do_cliente(Req("1.2.3.4, 200.10.20.30"), confiar_proxy=True) == "200.10.20.30"
    assert ip_do_cliente(Req("1.2.3.4"), confiar_proxy=False) == "10.0.0.1"
    assert ip_do_cliente(Req(None), confiar_proxy=True) == "10.0.0.1"
