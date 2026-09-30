"""Agente contra um LLM roteirizado e fontes falsas: testa o laço, não a qualidade do modelo."""
import json
from datetime import date

import httpx

from rag.agente import FERRAMENTAS, Agente, normalizar_semestre
from rag.busca import Evento, Resultado
from rag.llm import ClienteGroq, RespostaLLM


def chamada(nome: str, argumentos: dict | str, i: int = 0) -> dict:
    texto = argumentos if isinstance(argumentos, str) else json.dumps(argumentos)
    return {"id": f"c{i}", "type": "function", "function": {"name": nome, "arguments": texto}}


def responder(cobertura="total", resposta="ok", citacoes=()) -> dict:
    return chamada("responder", {"cobertura": cobertura, "resposta": resposta, "citacoes": list(citacoes)}, 99)


class LLMRoteirizado:
    """Devolve as rodadas na ordem e guarda o que recebeu."""

    def __init__(self, rodadas: list[list[dict]]):
        self.rodadas = iter(rodadas)
        self.pedidos: list[dict] = []

    def ferramentas(self, modelo, mensagens, ferramentas, escolha="required", max_tokens=1024):
        self.pedidos.append({"mensagens": [dict(m) for m in mensagens], "escolha": escolha})
        return RespostaLLM({"role": "assistant", "content": None, "tool_calls": next(self.rodadas)},
                           modelo, 100, 20, 10.0, 12.0, 1)


TRECHO = Resultado("rgcg-a073", "rgcg", "Art. 73 O trancamento não poderá ocorrer por mais de 4 semestres.",
                   "TÍTULO V > Art. 73", (73,), 22, 22, 0.9)
EVENTO = Evento(7, date(2027, 1, 21), date(2027, 1, 28), "Solicitação de trancamento de matrícula de 2027/1", 14)


class FontesFalsas:
    def __init__(self, falhar_calendario: bool = False):
        self.falhar_calendario = falhar_calendario
        self.consultas: list[tuple] = []

    def buscar_regulamento(self, consulta):
        self.consultas.append(("regulamento", consulta))
        return [TRECHO]

    def consultar_calendario(self, termo, inicio, fim):
        self.consultas.append(("calendario", termo, inicio, fim))
        if self.falhar_calendario:
            raise ConnectionError("banco fora do ar")
        return [EVENTO]


def agente(rodadas, fontes=None, **kw):
    llm = LLMRoteirizado(rodadas)
    return Agente(fontes or FontesFalsas(), llm, hoje=date(2026, 9, 29), **kw), llm


def test_pergunta_mista_usa_as_duas_fontes_e_cita_com_rotulos():
    fontes = FontesFalsas()
    a, llm = agente([
        [chamada("buscar_regulamento", {"consulta": "limite de trancamento"}, 1),
         chamada("consultar_calendario", {"termo": "trancamento 2027/1", "data_inicio": "2027-01-01",
                                          "data_fim": "2027-06-30"}, 2)],
        [responder(resposta="Até 4 semestres; de 21 a 28/01/2027.", citacoes=["T1", "E1"])],
    ], fontes)
    r = a.perguntar("Quantas vezes posso trancar e qual o prazo em 2027/1?")
    assert r.cobertura == "total" and r.chamadas_llm == 2 and not r.forcou_resposta
    assert [c[0] for c in r.citados] == ["T1", "E1"]
    assert r.citados[1][1] == "Calendário 2026, 21/01/2027 a 28/01/2027, p. 14"
    assert fontes.consultas[1] == ("calendario", "trancamento 2027/1", date(2027, 1, 1), date(2027, 6, 30))
    assert r.usou("buscar_regulamento") and r.usou("consultar_calendario")
    # o resultado da ferramenta volta ligado ao id da chamada, com os rótulos no texto
    ferramenta = [m for m in llm.pedidos[1]["mensagens"] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in ferramenta] == ["c1", "c2"]
    assert ferramenta[0]["content"].startswith("T1 (RGCG, Art. 73, p. 22)")
    assert "E1 (Calendário 2026, 21/01/2027 a 28/01/2027, p. 14)" in ferramenta[1]["content"]
    assert "Hoje é 2026-09-29" in llm.pedidos[0]["mensagens"][0]["content"]


def test_mesmo_trecho_em_duas_buscas_mantem_o_rotulo():
    a, _ = agente([
        [chamada("buscar_regulamento", {"consulta": "trancamento"}, 1)],
        [chamada("buscar_regulamento", {"consulta": "limite de trancamentos"}, 2)],
        [responder(citacoes=["T1"])],
    ])
    r = a.perguntar("x")
    assert list(r.trechos) == ["T1"] and r.passos[1].resultados == ["T1"]


def test_falha_da_ferramenta_volta_para_o_modelo_e_o_agente_segue():
    a, llm = agente([
        [chamada("consultar_calendario", {"termo": "feriado"}, 1)],
        [responder(cobertura="nenhuma", resposta="Não consegui consultar o calendário.")],
    ], FontesFalsas(falhar_calendario=True))
    r = a.perguntar("Quais os feriados?")
    assert r.erros_ferramenta == 1 and r.passos[0].erro == "falha interna (ConnectionError)"
    assert llm.pedidos[1]["mensagens"][-1]["content"] == "ERRO: falha interna (ConnectionError)"
    assert "banco fora do ar" not in llm.pedidos[1]["mensagens"][-1]["content"]  # detalhe interno não vaza
    assert r.cobertura == "nenhuma"


def test_argumentos_invalidos_viram_erro_explicado():
    a, llm = agente([
        [chamada("consultar_calendario", "{nao é json", 1),
         chamada("consultar_calendario", {"termo": "aulas", "data_inicio": "10/08/2026"}, 2),
         chamada("consultar_calendario", {"termo": "", "data_inicio": "2026-11-01"}, 3),
         chamada("consultar_calendario", {"termo": "x", "data_inicio": "2026-12-01", "data_fim": "2026-11-01"}, 4),
         chamada("apagar_tudo", {}, 5)],
        [responder(cobertura="nenhuma", resposta="Não sei.")],
    ])
    r = a.perguntar("x")
    erros = [p.erro for p in r.passos if p.ferramenta != "responder"]
    assert erros == ["argumentos não são JSON válido",
                     "data_inicio deve estar no formato AAAA-MM-DD, recebi '10/08/2026'",
                     "informe um termo ou as duas datas do intervalo",
                     "data_fim é anterior a data_inicio",
                     "ferramenta desconhecida: apagar_tudo"]
    assert r.erros_ferramenta == 5


def test_limite_de_passos_forca_a_resposta_no_ultimo():
    busca = [chamada("buscar_regulamento", {"consulta": "algo"}, 1)]
    a, llm = agente([busca, busca, [responder(citacoes=["T1"])]], max_passos=3)
    r = a.perguntar("x")
    assert [p["escolha"] for p in llm.pedidos] == ["required", "required",
                                                   {"type": "function", "function": {"name": "responder"}}]
    assert r.forcou_resposta and r.chamadas_llm == 3


def test_sem_resposta_valida_nem_no_ultimo_passo_devolve_nao_sei():
    busca = [chamada("buscar_regulamento", {"consulta": "algo"}, 1)]
    ruim = [chamada("responder", {"cobertura": "talvez", "resposta": "x", "citacoes": []}, 2)]
    a, llm = agente([busca, ruim], max_passos=2)
    r = a.perguntar("x")
    assert r.cobertura == "nenhuma" and r.citados == [] and "Não consegui" in r.resposta
    assert r.passos[-1].erro.startswith("cobertura deve ser")


def test_citacao_de_rotulo_nao_recebido_e_descartada():
    a, _ = agente([
        [chamada("buscar_regulamento", {"consulta": "nota"}, 1)],
        [responder(citacoes=["T1", "t1", "T7", "E1"])],
    ])
    r = a.perguntar("x")
    assert [c[0] for c in r.citados] == ["T1"] and r.citacoes_invalidas == 2


def test_cobertura_nenhuma_nao_leva_citacoes():
    a, _ = agente([
        [chamada("buscar_regulamento", {"consulta": "restaurante"}, 1)],
        [responder(cobertura="nenhuma", resposta="O regulamento não trata disso.", citacoes=["T1"])],
    ])
    assert a.perguntar("x").citados == []


def test_resposta_em_texto_sem_ferramenta_recebe_lembrete():
    class LLMTexto(LLMRoteirizado):
        def ferramentas(self, *args, **kw):
            r = super().ferramentas(*args, **kw)
            if len(self.pedidos) == 1:
                return RespostaLLM({"role": "assistant", "content": "acho que é em março"}, "m", 1, 1, 1.0, 1.0, 1)
            return r

    llm = LLMTexto([[], [responder(cobertura="nenhuma", resposta="Não sei.")]])
    r = Agente(FontesFalsas(), llm, hoje=date(2026, 9, 29)).perguntar("x")
    assert llm.pedidos[1]["mensagens"][-1] == {"role": "user",
                                               "content": "Use as ferramentas e termine chamando responder."}
    assert r.chamadas_llm == 2


def test_cliente_envia_ferramentas_e_repete_chamada_quebrada():
    pedidos: list = []
    quebrada = httpx.Response(400, json={"error": {"code": "tool_use_failed", "message": "Failed to call a function"}})
    ok = httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "tool_calls": [responder()]}}],
                                   "usage": {"prompt_tokens": 50, "completion_tokens": 5, "total_tokens": 55}})
    respostas = iter([quebrada, ok])

    def tratar(req):
        pedidos.append(json.loads(req.content))
        return next(respostas)

    c = ClienteGroq("gsk_teste", transporte=httpx.MockTransport(tratar), dormir=lambda s: None)
    r = c.ferramentas("openai/gpt-oss-20b", [], FERRAMENTAS)
    assert r.conteudo["tool_calls"][0]["function"]["name"] == "responder" and r.tentativas == 2
    assert pedidos[0]["tool_choice"] == "required" and len(pedidos[0]["tools"]) == 3
    assert "response_format" not in pedidos[0] and c.chamadas_quebradas == 1


def test_semestre_por_extenso_vira_o_formato_do_calendario():
    assert normalizar_semestre("início do segundo semestre de 2026", None, None) == "início do 2026/2"
    assert normalizar_semestre("trancamento 1º semestre 2027", None, None) == "trancamento 2027/1"
    # sem ano no termo, usa o do intervalo, se ele for de um ano só
    assert normalizar_semestre("segundo semestre", date(2026, 1, 1), date(2026, 12, 31)) == "2026/2"
    assert normalizar_semestre("segundo semestre", date(2026, 1, 1), date(2027, 6, 30)) == "segundo semestre"
    assert normalizar_semestre("feriado", None, None) == "feriado"
