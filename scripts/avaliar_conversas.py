"""Avalia a conversa com memória: o motor langgraph (com thread_id) contra o motor manual (pergunta sozinha).

Uso: python scripts/avaliar_conversas.py --motor manual|langgraph [--limite N]
Conjunto: dados/conversas.json (esboçado pelo Claude, revisado pelo Hugo).
Cache: resultados/conversas/<motor>.jsonl, uma linha por turno. Cada conversa é gravada inteira ou não é
gravada: a memória do langgraph fica no processo (InMemorySaver), então retomar no meio perderia o contexto.
Relatório: resultados/conversas.md, com os dois motores lado a lado quando os dois tiverem rodado.
Gasta cota do Groq: ~3 mil tokens por turno no agente, mais ~1,5 mil no juiz.

O que se mede: os turnos de acompanhamento ("e quando ele termina?") respondidos certo. O juiz recebe a
conversa até ali com as respostas de REFERÊNCIA dos turnos anteriores (não as do modelo), para julgar os
dois motores pelo mesmo contexto.
"""
import argparse
import json
import statistics
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from rag.agente import Agente, FontesBanco  # noqa: E402
from rag.agente_grafo import AgenteGrafo, checkpointer_em_memoria  # noqa: E402
from rag.juiz import REFERENCIA_SEM_RESPOSTA_AGENTE, SISTEMA_AGENTE, julgar  # noqa: E402
from rag.llm import ClienteGroq, ErroLLM  # noqa: E402

PASTA = RAIZ / "resultados" / "conversas"
MOTORES = ("manual", "langgraph")
HOJE = date(2026, 9, 29)  # o mesmo "hoje" fixo da avaliação do agente


def carregar() -> list[dict]:
    return json.loads((RAIZ / "dados" / "conversas.json").read_text(encoding="utf-8"))["conversas"]


def referencia(turno: dict) -> str:
    return turno.get("resposta", REFERENCIA_SEM_RESPOSTA_AGENTE)


def pergunta_para_o_juiz(turnos: list[dict], i: int) -> str:
    """A pergunta do turno i com a conversa anterior, para o juiz entender "e quando ele termina?"."""
    if i == 0:
        return turnos[0]["pergunta"]
    anteriores = "\n".join(f"Estudante: {t['pergunta']}\nAssistente: {referencia(t)}" for t in turnos[:i])
    return f"Conversa até aqui:\n{anteriores}\n\nPergunta atual do estudante: {turnos[i]['pergunta']}"


def criar_agente(motor: str, fontes, cliente):
    if motor == "manual":
        return Agente(fontes, cliente, hoje=HOJE)
    return AgenteGrafo(fontes, cliente, hoje=HOJE, checkpointer=checkpointer_em_memoria())


def conversar(agente, motor: str, conversa: dict) -> list:
    """Uma resposta por turno. O manual recebe cada pergunta sozinha; o langgraph, a conversa (thread_id)."""
    if motor == "manual":
        return [agente.perguntar(t["pergunta"]) for t in conversa["turnos"]]
    return [agente.perguntar(t["pergunta"], thread_id=conversa["id"]) for t in conversa["turnos"]]


def rodar(motor: str, limite: int | None) -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    arquivo = PASTA / f"{motor}.jsonl"
    feitas = {json.loads(linha)["conversa"] for linha in arquivo.open(encoding="utf-8")} if arquivo.exists() else set()
    pendentes = [c for c in carregar() if c["id"] not in feitas][:limite]
    print(f"{motor}: {len(feitas)} conversas já feitas, {len(pendentes)} agora")
    if not pendentes:
        return
    from rag.banco import conectar
    from rag.embeddings import Embedder

    embedder, cliente = Embedder("int8"), ClienteGroq()
    embedder.pergunta("aquecimento")
    agente = criar_agente(motor, FontesBanco(conectar(), embedder), cliente)
    for conversa in pendentes:
        turnos = conversa["turnos"]
        try:
            respostas = conversar(agente, motor, conversa)
            julgamentos = [julgar(cliente, pergunta_para_o_juiz(turnos, i), referencia(t), r.resposta,
                                  [(f"{rot} ({fonte})", texto) for rot, fonte, texto in r.citados],
                                  sistema=SISTEMA_AGENTE)
                           for i, (t, r) in enumerate(zip(turnos, respostas))]
        except ErroLLM as erro:
            print(f"  {conversa['id']}: parei ({erro}). Rode de novo para continuar.")
            return
        with arquivo.open("a", encoding="utf-8") as saida:
            for i, (t, r, j) in enumerate(zip(turnos, respostas, julgamentos), start=1):
                saida.write(json.dumps({
                    "conversa": conversa["id"], "turno": i, "motor": motor, "tipo": t["tipo"],
                    "pergunta": t["pergunta"], "referencia": referencia(t), "resposta": r.resposta,
                    "cobertura": r.cobertura, "citados": [c[0] + " " + c[1] for c in r.citados],
                    "ferramentas": [p.ferramenta for p in r.passos if p.ferramenta != "responder"],
                    "correta": j.conteudo["correta"], "fiel": j.conteudo["fiel"],
                    "justificativa": j.conteudo["justificativa"], "chamadas_llm": r.chamadas_llm,
                    "tokens_entrada": r.tokens_entrada, "tokens_saida": r.tokens_saida,
                    "ms": r.ms_llm + r.ms_ferramentas,
                }, ensure_ascii=False) + "\n")
        resumo = " ".join(f"t{i}={j.conteudo['correta']}" for i, j in enumerate(julgamentos, start=1))
        print(f"  {conversa['id']}: {resumo}")


def pct(n: int, total: int) -> str:
    return f"{n}/{total} ({100 * n / total:.0f}%)" if total else "-"


def relatorio() -> None:
    dados = {m: [json.loads(x) for x in (PASTA / f"{m}.jsonl").open(encoding="utf-8")]
             for m in MOTORES if (PASTA / f"{m}.jsonl").exists()}
    if not dados:
        return
    motores = list(dados)
    linhas = ["# Conversa com memória: motor langgraph x motor manual", "",
              "Gerado por scripts/avaliar_conversas.py com dados/conversas.json (conversas esboçadas pelo Claude e "
              "revisadas pelo Hugo). O manual recebe cada pergunta sozinha; o langgraph, a conversa inteira "
              "(até 3 turnos anteriores, só pergunta e resposta final). Juiz: openai/gpt-oss-120b, com a conversa "
              "anterior nas respostas de referência.", "",
              "| Métrica | " + " | ".join(motores) + " |", "|---|" + "---|" * len(motores)]

    def linha(nome, f):
        linhas.append(f"| {nome} | " + " | ".join(f(dados[m]) for m in motores) + " |")

    primeiro = lambda rs: [r for r in rs if r["turno"] == 1]  # noqa: E731
    seguintes = lambda rs: [r for r in rs if r["turno"] > 1]  # noqa: E731
    linha("Conversas", lambda rs: str(len({r["conversa"] for r in rs})))
    linha("Primeiro turno: correta", lambda rs: pct(sum(r["correta"] == "sim" for r in primeiro(rs)), len(primeiro(rs))))
    linha("Acompanhamento: correta", lambda rs: pct(sum(r["correta"] == "sim" for r in seguintes(rs)),
                                                    len(seguintes(rs))))
    linha("Acompanhamento: correta ou parcial", lambda rs: pct(sum(r["correta"] != "nao" for r in seguintes(rs)),
                                                               len(seguintes(rs))))
    linha("Acompanhamento: \"não sei\"", lambda rs: pct(sum(r["cobertura"] == "nenhuma" for r in seguintes(rs)),
                                                        len(seguintes(rs))))
    linha("Tokens de entrada por turno (acompanhamento)",
          lambda rs: f"{statistics.mean(r['tokens_entrada'] for r in seguintes(rs)):.0f}" if seguintes(rs) else "-")

    linhas += ["", "## Turnos de acompanhamento", ""]
    por_chave = {(r["conversa"], r["turno"]): {} for rs in dados.values() for r in seguintes(rs)}
    for m, rs in dados.items():
        for r in seguintes(rs):
            por_chave[(r["conversa"], r["turno"])][m] = r
    for (conversa, turno), porm in sorted(por_chave.items()):
        qualquer = next(iter(porm.values()))
        linhas.append(f"- **{conversa}, turno {turno}**: {qualquer['pergunta']}")
        for m in motores:
            if m in porm:
                r = porm[m]
                linhas.append(f"  - {m}: correta={r['correta']}, cobertura={r['cobertura']}. {r['justificativa']}")
    (RAIZ / "resultados" / "conversas.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print("relatório: resultados/conversas.md")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--motor", choices=MOTORES, required=True)
    parser.add_argument("--limite", type=int, help="número de conversas nesta rodada")
    args = parser.parse_args()
    rodar(args.motor, args.limite)
    relatorio()


if __name__ == "__main__":
    main()
