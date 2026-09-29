"""Cliente do Groq contra um servidor falso: nada sai para a internet e nenhuma cota é gasta."""
import json

import httpx
import pytest

from rag.llm import ClienteGroq, ErroLLM


class Relogio:
    def __init__(self):
        self.agora = 0.0
        self.esperas: list[float] = []

    def __call__(self) -> float:
        return self.agora

    def dormir(self, segundos: float) -> None:
        self.esperas.append(segundos)
        self.agora += segundos


def ok(conteudo: dict, total: int = 100) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(conteudo)}}],
                                     "usage": {"prompt_tokens": total - 10, "completion_tokens": 10,
                                               "total_tokens": total}})


def cliente(respostas: list[httpx.Response], relogio: Relogio, tpm: int = 8000, pedidos: list | None = None):
    fila = iter(respostas)

    def tratar(requisicao: httpx.Request) -> httpx.Response:
        if pedidos is not None:
            pedidos.append(json.loads(requisicao.content))
        return next(fila)

    return ClienteGroq("gsk_teste", tpm=tpm, transporte=httpx.MockTransport(tratar),
                       dormir=relogio.dormir, relogio=relogio)


SCHEMA = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"], "additionalProperties": False}


def test_pedido_tem_schema_strict_e_parametros_do_gpt_oss():
    pedidos: list = []
    r = cliente([ok({"a": 1})], Relogio(), pedidos=pedidos).json("openai/gpt-oss-20b", [], SCHEMA, "x")
    assert r.conteudo == {"a": 1} and r.tentativas == 1 and r.tokens_entrada == 90
    corpo = pedidos[0]
    assert corpo["response_format"]["json_schema"]["strict"] is True
    assert corpo["temperature"] == 0 and corpo["reasoning_effort"] == "low" and corpo["include_reasoning"] is False


def test_429_espera_o_retry_after_e_tenta_de_novo():
    relogio = Relogio()
    limite = httpx.Response(429, headers={"retry-after": "7"}, json={"error": "rate"})
    r = cliente([limite, ok({"a": 2})], relogio).json("m", [], SCHEMA, "x")
    assert r.conteudo == {"a": 2} and r.tentativas == 2
    assert relogio.esperas == [7.0]
    assert r.ms_total >= 7000 > r.ms  # a espera entra no total, não na latência da chamada


def test_espera_quando_o_proximo_pedido_passaria_do_limite_por_minuto():
    relogio = Relogio()
    c = cliente([ok({"a": 1}, total=2500), ok({"a": 1}, total=2500)], relogio, tpm=3000)
    c.json("m", [], SCHEMA, "x", estimativa_tokens=2000)
    relogio.agora = 10.0
    c.json("m", [], SCHEMA, "x", estimativa_tokens=2000)  # 2500 + 2000 > 3000: espera o 1º sair da janela
    assert relogio.esperas == [pytest.approx(50.1)]


def test_erro_4xx_nao_repete_e_json_quebrado_vira_erro():
    with pytest.raises(ErroLLM, match="HTTP 400"):
        cliente([httpx.Response(400, text="schema inválido")], Relogio()).json("m", [], SCHEMA, "x")
    quebrado = httpx.Response(200, json={"choices": [{"message": {"content": "não é json"}}], "usage": {}})
    with pytest.raises(ErroLLM, match="fora do formato"):
        cliente([quebrado], Relogio()).json("m", [], SCHEMA, "x")


def test_json_cortado_pelo_limite_tenta_uma_vez_com_o_dobro():
    pedidos: list = []
    cortado = httpx.Response(400, json={"error": {"code": "json_validate_failed", "failed_generation":
                                                  "max completion tokens reached before generating a valid document"}})
    c = cliente([cortado, ok({"a": 3})], Relogio(), pedidos=pedidos)
    assert c.json("m", [], SCHEMA, "x", max_tokens=800).conteudo == {"a": 3}
    assert [p["max_completion_tokens"] for p in pedidos] == [800, 1600]
    assert c.limites_dobrados == 1
    with pytest.raises(ErroLLM, match="HTTP 400"):  # só dobra uma vez
        cliente([cortado, cortado], Relogio()).json("m", [], SCHEMA, "x")


def test_desiste_depois_de_muitos_429():
    muitos = [httpx.Response(429, headers={"retry-after": "1"}) for _ in range(3)]
    with pytest.raises(ErroLLM, match="desisti"):
        cliente(muitos, Relogio()).json("m", [], SCHEMA, "x", max_tentativas=3)


def test_sem_chave_falha_cedo(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ErroLLM, match="GROQ_API_KEY"):
        ClienteGroq("")
