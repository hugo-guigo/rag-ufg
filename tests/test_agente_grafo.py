"""Motor LangGraph contra o mesmo LLM roteirizado do motor manual (tests/test_agente.py).

O teste principal roda os dois motores com o mesmo roteiro e exige o mesmo resultado E os mesmos
pedidos ao LLM: se o grafo mudasse a ordem das mensagens ou o momento de forçar a resposta, falharia.
"""
from dataclasses import asdict, dataclass
from datetime import date

import pytest
from langchain_core.messages import AIMessage

from rag.agente import Agente, Contagem, Passo
from rag.busca import Resultado
from rag.agente_grafo import AgenteGrafo, checkpointer_em_memoria, mensagem_do_modelo, para_api, recursion_limit
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


# ---- conversa com memória (bloco 2)

PERGUNTA_1 = "Quantas vezes posso trancar o curso?"
PERGUNTA_2 = "E qual o prazo para pedir em 2027/1?"


def conversa(rodadas, llm_classe=LLMRoteirizado):
    llm = llm_classe(rodadas)
    return AgenteGrafo(FontesFalsas(), llm, hoje=HOJE, checkpointer=checkpointer_em_memoria()), llm


def test_segundo_turno_ve_pergunta_e_resposta_do_primeiro_e_nao_as_ferramentas():
    a, llm = conversa([[chamada("buscar_regulamento", {"consulta": "trancar o curso"}, 1)],
                       [responder(resposta="Até 4 semestres (Art. 73).", citacoes=["T1"])],
                       [chamada("consultar_calendario", {"termo": "trancamento 2027/1"}, 2)],
                       [responder(resposta="De 21 a 28/01/2027.", citacoes=["E1"])]])
    a.perguntar(PERGUNTA_1, thread_id="t1")
    r2 = a.perguntar(PERGUNTA_2, thread_id="t1")

    mensagens = llm.pedidos[2]["mensagens"]  # primeira chamada do segundo turno
    assert [m["role"] for m in mensagens] == ["system", "user", "assistant", "user"]
    assert [m["content"] for m in mensagens[1:]] == [PERGUNTA_1, "Até 4 semestres (Art. 73).", PERGUNTA_2]
    assert not any(m["role"] == "tool" or m.get("tool_calls") for m in mensagens)
    # O turno conta só o que é dele: os rótulos recomeçam e as contagens zeram.
    assert r2.chamadas_llm == 2 and r2.tokens_entrada == 200
    assert [p.ferramenta for p in r2.passos] == ["consultar_calendario", "responder"]
    assert [c[0] for c in r2.citados] == ["E1"]


def test_conversas_diferentes_nao_se_misturam_e_pergunta_avulsa_nao_tem_memoria():
    a, llm = conversa([[responder(resposta="R1")], [responder(resposta="R2")], [responder(resposta="R3")]])
    a.perguntar(PERGUNTA_1, thread_id="t1")
    a.perguntar(PERGUNTA_2, thread_id="t2")
    a.perguntar(PERGUNTA_2)
    assert [len(p["mensagens"]) for p in llm.pedidos] == [2, 2, 2]  # sistema + pergunta, nas três


def test_memoria_guarda_so_os_ultimos_3_turnos():
    a, llm = conversa([[responder(resposta=f"R{i}")] for i in range(1, 6)])
    for i in range(1, 6):
        a.perguntar(f"pergunta {i}", thread_id="t1")
    ultima = [m["content"] for m in llm.pedidos[-1]["mensagens"][1:]]
    assert ultima == ["pergunta 2", "R2", "pergunta 3", "R3", "pergunta 4", "R4", "pergunta 5"]


def test_turno_sem_resposta_valida_fica_na_memoria_como_o_estudante_viu():
    a, llm = conversa([[], [], [], [], [responder(resposta="R2")]], LLMComTexto)
    a.max_passos = 1  # o primeiro turno responde em texto e acaba sem resposta válida
    r1 = a.perguntar(PERGUNTA_1, thread_id="t1")
    a.max_passos = 4
    a.perguntar(PERGUNTA_2, thread_id="t1")
    assert "Não consegui" in r1.resposta
    assert llm.pedidos[-1]["mensagens"][2] == {"role": "assistant", "content": r1.resposta}


def test_primeiro_turno_da_conversa_igual_a_pergunta_avulsa():
    for nome, roteiro in ROTEIROS.items():
        avulsa, llm_avulsa = rodar(AgenteGrafo, roteiro)
        a, llm = conversa(roteiro)
        r = a.perguntar("Quantas vezes posso trancar e qual o prazo em 2027/1?", thread_id="t1")
        assert sem_tempos(r) == sem_tempos(avulsa), nome
        assert llm.pedidos == llm_avulsa.pedidos, nome


def test_thread_id_sem_checkpointer_e_erro():
    a = AgenteGrafo(FontesFalsas(), LLMRoteirizado([]), hoje=HOJE)
    assert not a.conversa
    with pytest.raises(ValueError, match="checkpointer"):
        a.perguntar(PERGUNTA_1, thread_id="t1")


@dataclass
class ForaDaLista:
    x: int


def test_checkpoint_so_reconstroi_as_classes_do_projeto():
    serde = checkpointer_em_memoria().serde
    assert not isinstance(serde.loads_typed(serde.dumps_typed(ForaDaLista(1))), ForaDaLista)
    a, _ = conversa([[chamada("buscar_regulamento", {"consulta": "x"}, 1)], [responder(citacoes=["T1"])]])
    a.perguntar(PERGUNTA_1, thread_id="t1")
    salvo = a.grafo_conversa.get_state({"configurable": {"thread_id": "t1"}}).values
    assert isinstance(salvo["contagem"], Contagem) and all(isinstance(p, Passo) for p in salvo["registros"])
    assert isinstance(salvo["trechos"]["T1"], Resultado)
    assert salvo["historico"] == [{"pergunta": PERGUNTA_1, "resposta": "ok"}]


def test_argumentos_que_nao_sao_texto_viram_erro_como_no_motor_manual():
    roteiro = [[{"id": "c1", "type": "function", "function": {"name": "buscar_regulamento", "arguments": 7}}],
               [responder(cobertura="nenhuma", resposta="Não sei.")]]
    manual, _ = rodar(Agente, roteiro)
    grafo, _ = rodar(AgenteGrafo, roteiro)
    assert sem_tempos(grafo) == sem_tempos(manual)
