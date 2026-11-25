"""O conjunto de conversas e o roteiro do scripts/avaliar_conversas.py, com o LLM falso (sem cota)."""
import importlib.util
import json
from pathlib import Path

from tests.test_agente import FontesFalsas, LLMRoteirizado, responder

RAIZ = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("avaliar_conversas", RAIZ / "scripts" / "avaliar_conversas.py")
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)


def test_conjunto_de_conversas_bem_formado():
    conversas = script.carregar()
    anotadas = {p["id"]: p for p in json.loads((RAIZ / "dados" / "avaliacao.json").read_text(encoding="utf-8"))}
    assert len({c["id"] for c in conversas}) == len(conversas) >= 10
    for c in conversas:
        assert 2 <= len(c["turnos"]) <= 3, c["id"]
        for t in c["turnos"]:
            assert t["tipo"] in ("regulamento", "calendario", "misto", "sem_resposta"), c["id"]
            assert ("resposta" in t) == (t["tipo"] != "sem_resposta"), c["id"]
            assert t.get("origem") is None or t["origem"] in anotadas, c["id"]
        primeiro = c["turnos"][0]
        if primeiro.get("origem"):  # o primeiro turno é a pergunta anotada, com a mesma referência
            assert primeiro["pergunta"] == anotadas[primeiro["origem"]]["pergunta"], c["id"]
            assert primeiro.get("resposta") == anotadas[primeiro["origem"]].get("resposta"), c["id"]


def test_juiz_recebe_a_conversa_com_as_respostas_de_referencia():
    turnos = [{"pergunta": "Quando começa 2026/2?", "resposta": "10/08/2026."},
              {"pergunta": "E quando ele termina?", "resposta": "12/12/2026."}]
    assert script.pergunta_para_o_juiz(turnos, 0) == "Quando começa 2026/2?"
    texto = script.pergunta_para_o_juiz(turnos, 1)
    assert "Estudante: Quando começa 2026/2?\nAssistente: 10/08/2026." in texto
    assert texto.endswith("Pergunta atual do estudante: E quando ele termina?")


def test_manual_pergunta_sozinho_e_langgraph_leva_a_conversa():
    conversa = {"id": "v01", "turnos": [{"pergunta": "Quando começa 2026/2?"}, {"pergunta": "E quando termina?"}]}
    roteiro = [[responder(resposta="Em 10/08/2026.")], [responder(resposta="Em 12/12/2026.")]]
    for motor, mensagens_no_segundo in (("manual", 2), ("langgraph", 4)):
        llm = LLMRoteirizado(roteiro)
        agente = script.criar_agente(motor, FontesFalsas(), llm)
        respostas = script.conversar(agente, motor, conversa)
        assert [r.resposta for r in respostas] == ["Em 10/08/2026.", "Em 12/12/2026."]
        assert len(llm.pedidos[1]["mensagens"]) == mensagens_no_segundo, motor  # sistema + (histórico) + pergunta
