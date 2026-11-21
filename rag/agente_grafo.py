"""Segundo motor do agente, em LangGraph: o mesmo trabalho do laço de rag/agente.py, como um grafo.

    START -> modelo --(pediu ferramentas)--> ferramentas --(resposta válida ou limite)--> END
               ^  |                              |
               |  +--(texto, sem ferramenta)--+  |
               +------------------------------+--+  (volta enquanto houver passos)

- Estado: as mensagens (com o redutor add_messages, que junta as novas às antigas) e o que o
  RespostaAgente precisa no fim: passos registrados, rótulos T1/E1, resposta final e contagens.
- Nó modelo: uma chamada ao LLM. Na última volta, força a ferramenta responder, como o motor manual.
- Nó ferramentas: executa cada chamada com a mesma função do motor manual (executar_chamada).
- Arestas condicionais decidem o próximo nó a partir do estado.

Ferramentas, validação, prompt e cliente HTTP são os mesmos do motor manual, de propósito: a
comparação entre os dois mede só o motor (docs/specs/langgraph.md, decisões 1 e 2).
"""
from __future__ import annotations

import json
from datetime import date
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from rag.agente import (FERRAMENTAS, FORCAR_RESPOSTA, LEMBRETE, MAX_PASSOS, SISTEMA, Contagem, Fontes, Passo,
                        RespostaAgente, concluir, executar_chamada)
from rag.busca import Evento, Resultado
from rag.llm import ClienteGroq
from rag.resposta import MODELO_RESPOSTA


def recursion_limit(max_passos: int) -> int:
    """Rede de segurança do LangGraph, além do contador de passos do estado.

    Cada volta são dois nós (modelo e ferramentas): 2 * max_passos cabe com folga de 2. Com o padrão
    (MAX_PASSOS = 4), dá 10. O padrão do LangGraph nesta versão é 10.007, que deixaria um bug no
    contador rodar (e gastar cota) por muito tempo antes de parar.
    """
    return 2 * max_passos + 2


class Estado(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    # Os campos abaixo não têm redutor: cada nó devolve o valor novo inteiro, e a entrada de cada
    # pergunta os zera. Com a memória (bloco 2), isso evita que um turno herde contagens do anterior.
    passos: int  # chamadas ao LLM neste turno
    registros: list[Passo]
    trechos: dict[str, Resultado]
    eventos: dict[str, Evento]
    final: dict | None
    forcou: bool
    contagem: Contagem  # tokens e tempos do turno; o nó modelo devolve uma cópia somada


def para_api(mensagens: list[AnyMessage]) -> list[dict]:
    """Mensagens do estado no formato da API do Groq.

    Não usamos convert_to_openai_messages do langchain-core: ele descarta a chamada de ferramenta cujos
    argumentos não são JSON válido, mas mantém a resposta da ferramenta para ela, e a API recusa uma
    resposta sem a chamada correspondente. Aqui as chamadas vão exatamente como o modelo mandou
    (guardadas em additional_kwargs), igual ao motor manual.
    """
    saida: list[dict] = []
    for m in mensagens:
        if isinstance(m, HumanMessage):
            saida.append({"role": "user", "content": m.content})
        elif isinstance(m, AIMessage):
            item: dict = {"role": "assistant", "content": m.content or ""}
            if m.additional_kwargs.get("tool_calls"):
                item["tool_calls"] = m.additional_kwargs["tool_calls"]
            saida.append(item)
        elif isinstance(m, ToolMessage):
            saida.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
        else:
            raise TypeError(f"mensagem inesperada no estado: {type(m).__name__}")
    return saida


def mensagem_do_modelo(conteudo: dict) -> AIMessage:
    """A resposta do LLM como AIMessage, guardando as chamadas originais em additional_kwargs.

    tool_calls (argumentos já lidos) e invalid_tool_calls ficam preenchidos para quem usa a API do
    LangChain; o envio de volta ao modelo usa as originais (ver para_api).
    """
    brutas = conteudo.get("tool_calls") or []
    validas, invalidas = [], []
    for c in brutas:
        nome, texto = c["function"]["name"], c["function"].get("arguments") or "{}"
        try:
            argumentos = json.loads(texto)
            if not isinstance(argumentos, dict):
                raise ValueError("não é objeto")
            validas.append({"name": nome, "args": argumentos, "id": c["id"], "type": "tool_call"})
        except ValueError as erro:
            invalidas.append({"name": nome, "args": texto, "id": c["id"], "error": str(erro),
                              "type": "invalid_tool_call"})
    return AIMessage(content=conteudo.get("content") or "", tool_calls=validas, invalid_tool_calls=invalidas,
                     additional_kwargs={"tool_calls": brutas} if brutas else {})


class AgenteGrafo:
    """O motor LangGraph, com a mesma interface do Agente manual: perguntar(pergunta) -> RespostaAgente."""

    def __init__(self, fontes: Fontes, cliente: ClienteGroq, modelo: str = MODELO_RESPOSTA,
                 max_passos: int = MAX_PASSOS, hoje: date | None = None, checkpointer=None):
        self.fontes, self.cliente, self.modelo, self.max_passos = fontes, cliente, modelo, max_passos
        self.hoje = hoje or date.today()
        self.grafo = self._construir().compile(checkpointer=checkpointer)

    # ---- nós

    def _modelo(self, estado: Estado) -> dict:
        passo = estado["passos"] + 1
        ultimo = passo >= self.max_passos
        sistema = {"role": "system", "content": SISTEMA.format(hoje=self.hoje.isoformat())}
        r = self.cliente.ferramentas(self.modelo, [sistema, *para_api(estado["messages"])], FERRAMENTAS,
                                     FORCAR_RESPOSTA if ultimo else "required", max_tokens=800)
        contagem = Contagem(**vars(estado["contagem"]))  # cópia: o estado anterior fica intacto
        contagem.somar(r)
        resposta = mensagem_do_modelo(r.conteudo)
        novas: list[AnyMessage] = [resposta]
        if not resposta.additional_kwargs.get("tool_calls"):  # texto, sem ferramenta: lembrete
            novas.append(HumanMessage(LEMBRETE))
        return {"messages": novas, "passos": passo, "forcou": ultimo, "contagem": contagem}

    def _ferramentas(self, estado: Estado) -> dict:
        trechos, eventos = dict(estado["trechos"]), dict(estado["eventos"])
        registros = list(estado["registros"])
        final = estado["final"]
        respostas: list[AnyMessage] = []
        for chamada in estado["messages"][-1].additional_kwargs["tool_calls"]:
            conteudo, registro, resposta = executar_chamada(chamada, self.fontes, trechos, eventos)
            registros.append(registro)
            final = resposta or final
            respostas.append(ToolMessage(conteudo, tool_call_id=chamada["id"]))
        return {"messages": respostas, "registros": registros, "trechos": trechos, "eventos": eventos,
                "final": final}

    # ---- arestas condicionais

    def _depois_do_modelo(self, estado: Estado) -> str:
        ultima = estado["messages"][-1]
        if isinstance(ultima, AIMessage) and ultima.additional_kwargs.get("tool_calls"):
            return "ferramentas"
        # Respondeu em texto (a última mensagem é o lembrete): tenta de novo se ainda houver passos.
        return "modelo" if estado["passos"] < self.max_passos else END

    def _depois_das_ferramentas(self, estado: Estado) -> str:
        if estado["final"] is not None or estado["passos"] >= self.max_passos:
            return END
        return "modelo"

    def _construir(self) -> StateGraph:
        g = StateGraph(Estado)
        g.add_node("modelo", self._modelo)
        g.add_node("ferramentas", self._ferramentas)
        g.add_edge(START, "modelo")
        g.add_conditional_edges("modelo", self._depois_do_modelo, ["ferramentas", "modelo", END])
        g.add_conditional_edges("ferramentas", self._depois_das_ferramentas, ["modelo", END])
        return g

    # ---- interface pública

    def perguntar(self, pergunta: str) -> RespostaAgente:
        entrada = {"messages": [HumanMessage(pergunta)], "passos": 0, "registros": [], "trechos": {},
                   "eventos": {}, "final": None, "forcou": False, "contagem": Contagem()}
        estado = self.grafo.invoke(entrada, {"recursion_limit": recursion_limit(self.max_passos)})
        return concluir(pergunta, estado["final"], estado["registros"], estado["contagem"], estado["forcou"],
                        self.modelo, estado["trechos"], estado["eventos"])
