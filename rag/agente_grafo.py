"""Segundo motor do agente, em LangGraph: o mesmo trabalho do laço de rag/agente.py, como um grafo.

    START -> modelo --(pediu ferramentas)--> ferramentas --(resposta válida ou limite)--> memoria -> END
               ^  |                              |
               |  +--(texto, sem ferramenta)--+  |
               +------------------------------+--+  (volta enquanto houver passos)

- Estado: as mensagens (com o redutor add_messages, que junta as novas às antigas) e o que o
  RespostaAgente precisa no fim: passos registrados, rótulos T1/E1, resposta final e contagens.
- Nó modelo: uma chamada ao LLM. Na última volta, força a ferramenta responder, como o motor manual.
- Nó ferramentas: executa cada chamada com a mesma função do motor manual (executar_chamada).
- Nó memoria: guarda a pergunta e a resposta final do turno (até TURNOS_NA_MEMORIA turnos).
- Arestas condicionais decidem o próximo nó a partir do estado.

Conversa: com um checkpointer e um thread_id, o estado de cada conversa fica salvo e a pergunta
seguinte continua dali. O modelo vê dos turnos anteriores só a pergunta e a resposta final; as saídas
das ferramentas ficam no turno em que foram buscadas (docs/specs/langgraph.md, decisão 5).

Ferramentas, validação, prompt e cliente HTTP são os mesmos do motor manual, de propósito: a
comparação entre os dois mede só o motor (docs/specs/langgraph.md, decisões 1 e 2).
"""
from __future__ import annotations

import json
from datetime import date
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, RemoveMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import REMOVE_ALL_MESSAGES, add_messages

from rag.agente import (FERRAMENTAS, FORCAR_RESPOSTA, LEMBRETE, MAX_PASSOS, SEM_RESPOSTA, SISTEMA, Contagem, Fontes,
                        Passo, RespostaAgente, concluir, executar_chamada)
from rag.busca import Evento, Resultado
from rag.llm import ClienteGroq
from rag.resposta import MODELO_RESPOSTA

TURNOS_NA_MEMORIA = 3

# O checkpointer serializa o estado. Só estas classes do projeto podem ser reconstruídas ao ler um
# checkpoint; o padrão da biblioteca aceita qualquer classe (com aviso), o que é arriscado com um banco.
# Uma tupla volta como lista (Resultado.artigos), sem efeito: os campos do turno são zerados a cada
# pergunta e só o histórico, de textos, passa de um turno para o outro.
SERIALIZADOR = JsonPlusSerializer(allowed_msgpack_modules=[Passo, Contagem, Resultado, Evento])


def checkpointer_em_memoria() -> InMemorySaver:
    """Para os testes, a avaliação e a API até o bloco 4 (Postgres). Some quando o processo para."""
    return InMemorySaver(serde=SERIALIZADOR)


def recursion_limit(max_passos: int) -> int:
    """Rede de segurança do LangGraph, além do contador de passos do estado.

    Cada volta são dois nós (modelo e ferramentas), mais o nó memoria no fim: 2 * max_passos + 1, com
    folga de 1. Com o padrão (MAX_PASSOS = 4), dá 10. O padrão do LangGraph nesta versão é 10.007, que deixaria um bug no
    contador rodar (e gastar cota) por muito tempo antes de parar.
    """
    return 2 * max_passos + 2


class Estado(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]  # só as do turno atual (a entrada apaga as antigas)
    historico: list[dict]  # {"pergunta", "resposta"} dos turnos anteriores; o único campo que passa de turno
    # Os campos abaixo não têm redutor: cada nó devolve o valor novo inteiro, e a entrada de cada
    # pergunta os zera, para um turno não herdar contagens do anterior.
    pergunta: str
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
        except (ValueError, TypeError) as erro:  # TypeError: argumentos que nem são texto
            invalidas.append({"name": nome, "args": str(texto), "id": c["id"], "error": str(erro),
                              "type": "invalid_tool_call"})
    return AIMessage(content=conteudo.get("content") or "", tool_calls=validas, invalid_tool_calls=invalidas,
                     additional_kwargs={"tool_calls": brutas} if brutas else {})


class AgenteGrafo:
    """O motor LangGraph, com a mesma interface do Agente manual: perguntar(pergunta) -> RespostaAgente."""

    def __init__(self, fontes: Fontes, cliente: ClienteGroq, modelo: str = MODELO_RESPOSTA,
                 max_passos: int = MAX_PASSOS, hoje: date | None = None, checkpointer=None):
        self.fontes, self.cliente, self.modelo, self.max_passos = fontes, cliente, modelo, max_passos
        self.hoje = hoje or date.today()
        g = self._construir()
        self.grafo = g.compile()  # pergunta avulsa: sem checkpoint, como o motor manual
        self.grafo_conversa = g.compile(checkpointer=checkpointer) if checkpointer is not None else None

    @property
    def conversa(self) -> bool:
        """Se aceita thread_id (a API usa isto para recusar a conversa sem memória)."""
        return self.grafo_conversa is not None

    # ---- nós

    def _modelo(self, estado: Estado) -> dict:
        passo = estado["passos"] + 1
        ultimo = passo >= self.max_passos
        sistema = {"role": "system", "content": SISTEMA.format(hoje=self.hoje.isoformat())}
        anteriores = []
        for turno in estado.get("historico") or []:
            anteriores += [{"role": "user", "content": turno["pergunta"]},
                           {"role": "assistant", "content": turno["resposta"]}]
        r = self.cliente.ferramentas(self.modelo, [sistema, *anteriores, *para_api(estado["messages"])],
                                     FERRAMENTAS,
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

    def _memoria(self, estado: Estado) -> dict:
        # Guarda o que o estudante viu, inclusive o "Não consegui concluir" quando não houve resposta válida.
        resposta = (estado["final"] or SEM_RESPOSTA)["resposta"]
        historico = [*(estado.get("historico") or []), {"pergunta": estado["pergunta"], "resposta": resposta}]
        return {"historico": historico[-TURNOS_NA_MEMORIA:]}

    # ---- arestas condicionais

    def _depois_do_modelo(self, estado: Estado) -> str:
        ultima = estado["messages"][-1]
        if isinstance(ultima, AIMessage) and ultima.additional_kwargs.get("tool_calls"):
            return "ferramentas"
        # Respondeu em texto (a última mensagem é o lembrete): tenta de novo se ainda houver passos.
        return "modelo" if estado["passos"] < self.max_passos else "memoria"

    def _depois_das_ferramentas(self, estado: Estado) -> str:
        if estado["final"] is not None or estado["passos"] >= self.max_passos:
            return "memoria"
        return "modelo"

    def _construir(self) -> StateGraph:
        g = StateGraph(Estado)
        g.add_node("modelo", self._modelo)
        g.add_node("ferramentas", self._ferramentas)
        g.add_node("memoria", self._memoria)
        g.add_edge(START, "modelo")
        g.add_conditional_edges("modelo", self._depois_do_modelo, ["ferramentas", "modelo", "memoria"])
        g.add_conditional_edges("ferramentas", self._depois_das_ferramentas, ["modelo", "memoria"])
        g.add_edge("memoria", END)
        return g

    # ---- interface pública

    def perguntar(self, pergunta: str, thread_id: str | None = None) -> RespostaAgente:
        """Sem thread_id: pergunta avulsa. Com thread_id: continua a conversa salva no checkpointer."""
        # RemoveMessage(REMOVE_ALL_MESSAGES) apaga as mensagens do turno anterior antes de juntar a pergunta
        # nova; sem isso o add_messages acumularia tudo, inclusive as saídas das ferramentas.
        entrada = {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), HumanMessage(pergunta)],
                   "pergunta": pergunta, "passos": 0, "registros": [], "trechos": {}, "eventos": {},
                   "final": None, "forcou": False, "contagem": Contagem()}
        config: dict = {"recursion_limit": recursion_limit(self.max_passos)}
        if thread_id is None:
            grafo = self.grafo  # sem checkpointer o estado nasce vazio: não há histórico
        elif self.grafo_conversa is None:
            raise ValueError("conversa com thread_id exige um checkpointer")
        else:
            grafo = self.grafo_conversa  # sem "historico" na entrada: vale o que está salvo na conversa
            config["configurable"] = {"thread_id": thread_id}
        estado = grafo.invoke(entrada, config)
        return concluir(pergunta, estado["final"], estado["registros"], estado["contagem"], estado["forcou"],
                        self.modelo, estado["trechos"], estado["eventos"])
