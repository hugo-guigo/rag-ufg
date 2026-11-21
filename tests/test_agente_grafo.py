"""Motor LangGraph contra o mesmo LLM roteirizado do motor manual (tests/test_agente.py).

O teste principal roda os dois motores com o mesmo roteiro e exige o mesmo resultado E os mesmos
pedidos ao LLM: se o grafo mudasse a ordem das mensagens ou o momento de forçar a resposta, falharia.
"""
from dataclasses import asdict
from datetime import date

import pytest
from langchain_core.messages import AIMessage

from rag.agente import Agente
from rag.agente_grafo import AgenteGrafo, mensagem_do_modelo, para_api, recursion_limit
from rag.llm import RespostaLLM
from tests.test_agente import FontesFalsas, LLMRoteirizado, chamada, responder

HOJE = date(2026, 9, 29)
BUSCA = [chamada("buscar_regulamento", {"consulta": "algo"}, 1)]

ROTEIROS = {
    "com_ferramentas": [
        [chamada("buscar_regulamento", {"consulta": "limite de trancamento"}, 1),
         chamada("consultar_calendario", {"termo": "trancamento 2027/1", "data_inicio": "2027-01-01",
                                          "data_fim": "2027-06-30"}, 2)],
        [responder(resposta="Até 4 semestres; de 21 a 28/01/2027.", citacoes=["T1", "E1", "T9"])],
    ],
    "mesmo_trecho_duas_buscas": [
        [chamada("buscar_regulamento", {"consulta": "trancamento"}, 1)],
        [chamada("buscar_regulamento", {"consulta": "limite de trancamentos"}, 2)],
        [responder(citacoes=["T1"])],
    ],
    "argumentos_invalidos": [
        [chamada("consultar_calendario", "{nao é json", 1),
         chamada("consultar_calendario", {"termo": "aulas", "data_inicio": "10/08/2026"}, 2),
         chamada("apagar_tudo", {}, 3)],
        [responder(cobertura="nenhuma", resposta="Não sei.")],
    ],
    "limite_forca_resposta": [BUSCA, BUSCA, BUSCA, [responder(citacoes=["T1"])]],
    "sem_resposta_valida": [BUSCA, BUSCA, BUSCA,
                            [chamada("responder", {"cobertura": "talvez", "resposta": "x", "citacoes": []}, 2)]],
}


class LLMComTexto(LLMRoteirizado):
    """Na primeira chamada responde em texto, sem ferramenta."""

    def ferramentas(self, *args, **kw):
        r = super().ferramentas(*args, **kw)
        if len(self.pedidos) == 1:
            return RespostaLLM({"role": "assistant", "content": "acho que é em março"}, "m", 7, 3, 1.0, 1.0, 1)
        return r


def sem_tempos(r) -> dict:
    d = asdict(r)
    for chave in ("ms_llm", "ms_llm_total", "ms_ferramentas"):
        d.pop(chave)
    for p in d["passos"]:
        p.pop("ms")
    return d


def rodar(motor, roteiro, llm_classe=LLMRoteirizado, fontes=None, **kw):
    llm = llm_classe(roteiro)
    a = motor(fontes or FontesFalsas(), llm, hoje=HOJE, **kw)
    return a.perguntar("Quantas vezes posso trancar e qual o prazo em 2027/1?"), llm


@pytest.mark.parametrize("nome", ROTEIROS)
def test_os_dois_motores_dao_o_mesmo_resultado_e_fazem_os_mesmos_pedidos(nome):
    manual, llm_manual = rodar(Agente, ROTEIROS[nome])
    grafo, llm_grafo = rodar(AgenteGrafo, ROTEIROS[nome])
    assert sem_tempos(grafo) == sem_tempos(manual)
    assert llm_grafo.pedidos == llm_manual.pedidos


def test_mesmo_resultado_com_resposta_em_texto_e_lembrete():
    roteiro = [[], [responder(cobertura="nenhuma", resposta="Não sei.")]]
    manual, llm_manual = rodar(Agente, roteiro, LLMComTexto)
    grafo, llm_grafo = rodar(AgenteGrafo, roteiro, LLMComTexto)
    assert sem_tempos(grafo) == sem_tempos(manual)
    assert llm_grafo.pedidos == llm_manual.pedidos
    assert llm_grafo.pedidos[1]["mensagens"][-1] == {"role": "user",
                                                    "content": "Use as ferramentas e termine chamando responder."}


def test_caminho_com_ferramenta_cita_com_rotulos():
    r, llm = rodar(AgenteGrafo, ROTEIROS["com_ferramentas"])
    assert r.cobertura == "total" and r.chamadas_llm == 2 and not r.forcou_resposta
    assert [c[0] for c in r.citados] == ["T1", "E1"] and r.citacoes_invalidas == 1
    assert r.tokens_entrada == 200 and r.tokens_saida == 40  # 2 chamadas de 100/20 no LLM falso
    ferramenta = [m for m in llm.pedidos[1]["mensagens"] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in ferramenta] == ["c1", "c2"]


def test_erro_de_ferramenta_volta_para_o_modelo():
    roteiro = [[chamada("consultar_calendario", {"termo": "feriado"}, 1)],
               [responder(cobertura="nenhuma", resposta="Não consegui consultar o calendário.")]]
    r, llm = rodar(AgenteGrafo, roteiro, fontes=FontesFalsas(falhar_calendario=True))
    assert r.erros_ferramenta == 1 and r.passos[0].erro == "falha interna (ConnectionError)"
    assert llm.pedidos[1]["mensagens"][-1]["content"] == "ERRO: falha interna (ConnectionError)"


def test_estouro_do_limite_forca_a_resposta_no_ultimo_passo():
    r, llm = rodar(AgenteGrafo, [BUSCA, BUSCA, [responder(citacoes=["T1"])]], max_passos=3)
    assert [p["escolha"] for p in llm.pedidos] == ["required", "required",
                                                   {"type": "function", "function": {"name": "responder"}}]
    assert r.forcou_resposta and r.chamadas_llm == 3


def test_texto_ate_o_fim_termina_com_nao_consegui_sem_estourar_o_grafo():
    class SoTexto(LLMRoteirizado):
        def ferramentas(self, modelo, mensagens, ferramentas, escolha="required", max_tokens=1024):
            self.pedidos.append({"mensagens": mensagens, "escolha": escolha})
            return RespostaLLM({"role": "assistant", "content": "não sei"}, modelo, 1, 1, 1.0, 1.0, 1)

    r, llm = rodar(AgenteGrafo, [], SoTexto)
    assert r.chamadas_llm == 4 and "Não consegui" in r.resposta and r.cobertura == "nenhuma"


def test_recursion_limit_e_a_rede_de_seguranca():
    assert recursion_limit(4) == 10
    # 4 voltas de modelo e ferramentas são 8 nós: cabem com folga
    r, _ = rodar(AgenteGrafo, ROTEIROS["limite_forca_resposta"])
    assert r.chamadas_llm == 4


def test_chamada_com_json_invalido_volta_igual_para_a_api():
    brutas = [{"id": "c1", "type": "function", "function": {"name": "consultar_calendario", "arguments": "{x"}},
              {"id": "c2", "type": "function", "function": {"name": "buscar_regulamento",
                                                            "arguments": '{"consulta": "y"}'}}]
    m = mensagem_do_modelo({"role": "assistant", "content": None, "tool_calls": brutas})
    assert [c["id"] for c in m.tool_calls] == ["c2"] and [c["id"] for c in m.invalid_tool_calls] == ["c1"]
    assert para_api([m]) == [{"role": "assistant", "content": "", "tool_calls": brutas}]
    assert para_api([AIMessage("oi")]) == [{"role": "assistant", "content": "oi"}]
