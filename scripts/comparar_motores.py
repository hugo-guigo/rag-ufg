"""Compara os motores manual e langgraph nas mesmas perguntas (rodadas de scripts/avaliar_agente.py).

Uso: python scripts/comparar_motores.py
Lê resultados/agente/<motor>/<conjunto>.jsonl e escreve resultados/motores.md. Só compara as perguntas que
os dois motores já responderam, para a diferença ser do motor e não do conjunto.
"""
import json
import statistics
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from avaliar_agente import PASTA, ferramenta_certa, pct  # noqa: E402
from rag.metricas import percentil  # noqa: E402

MOTORES = ("manual", "langgraph")
CONJUNTOS = {"avaliacao": "50 perguntas anotadas", "teste": "10 perguntas em linguagem de aluno"}


def carregar(motor: str, conjunto: str) -> dict[str, dict]:
    arquivo = PASTA / motor / f"{conjunto}.jsonl"
    if not arquivo.exists():
        return {}
    return {r["id"]: r for r in map(json.loads, arquivo.open(encoding="utf-8"))}


def secao(conjunto: str) -> list[str]:
    por_motor = {m: carregar(m, conjunto) for m in MOTORES}
    ids = sorted(set.intersection(*(set(d) for d in por_motor.values())))
    if not ids:
        return []
    linhas = [f"## {CONJUNTOS[conjunto]} ({len(ids)} em comum)", "",
              "| Métrica | " + " | ".join(MOTORES) + " |", "|---|" + "---|" * len(MOTORES)]

    def linha(nome, f):
        linhas.append(f"| {nome} | " + " | ".join(f([por_motor[m][i] for i in ids]) for m in MOTORES) + " |")

    com_resposta = lambda rs: [r for r in rs if r["tipo"] != "sem_resposta"]  # noqa: E731
    linha("Correta (juiz: sim)", lambda rs: pct(sum(r["correta"] == "sim" for r in rs), len(rs)))
    linha("Correta ou parcial", lambda rs: pct(sum(r["correta"] != "nao" for r in rs), len(rs)))
    linha("Fiel às fontes citadas", lambda rs: pct(sum(r["fiel"] for r in rs if r["cobertura"] != "nenhuma"),
                                                    sum(r["cobertura"] != "nenhuma" for r in rs)))
    linha("Ferramenta certa", lambda rs: pct(sum(ferramenta_certa(r) for r in com_resposta(rs)), len(com_resposta(rs))))
    linha("\"Não sei\" nas sem resposta", lambda rs: pct(sum(r["cobertura"] == "nenhuma" for r in rs
                                                             if r["tipo"] == "sem_resposta"),
                                                         sum(r["tipo"] == "sem_resposta" for r in rs)))
    linha("Chamadas ao LLM (média)", lambda rs: f"{statistics.mean(r['chamadas_llm'] for r in rs):.2f}")
    linha("Respostas forçadas no último passo", lambda rs: str(sum(r["forcou_resposta"] for r in rs)))
    linha("Erros de ferramenta", lambda rs: str(sum(r["erros_ferramenta"] for r in rs)))
    linha("Citações inválidas", lambda rs: str(sum(r["citacoes_invalidas"] for r in rs)))
    linha("Tokens por pergunta (entrada / saída)",
          lambda rs: f"{statistics.mean(r['tokens_entrada'] for r in rs):.0f} / "
                     f"{statistics.mean(r['tokens_saida'] for r in rs):.0f}")
    linha("Latência p50 / p95 (ms)",
          lambda rs: f"{percentil([r['ms_llm'] + r['ms_ferramentas'] for r in rs], 0.5):.0f} / "
                     f"{percentil([r['ms_llm'] + r['ms_ferramentas'] for r in rs], 0.95):.0f}")

    manual, grafo = por_motor["manual"], por_motor["langgraph"]
    so_manual = [i for i in ids if manual[i]["correta"] == "sim" and grafo[i]["correta"] != "sim"]
    so_grafo = [i for i in ids if grafo[i]["correta"] == "sim" and manual[i]["correta"] != "sim"]
    linhas += ["", f"Só o manual acertou: {', '.join(so_manual) or 'nenhuma'}. "
                   f"Só o langgraph acertou: {', '.join(so_grafo) or 'nenhuma'}.", ""]
    return linhas


def main() -> None:
    corpo = [linha for conjunto in CONJUNTOS for linha in secao(conjunto)]
    if not corpo:
        print("nada para comparar: rode scripts/avaliar_agente.py com --motor manual e --motor langgraph")
        return
    cabecalho = ["# Motor manual x motor LangGraph (mesmas perguntas, mesmos dias)", "",
                 "Gerado por scripts/comparar_motores.py. Os dois motores usam as mesmas ferramentas, o mesmo prompt, "
                 "o mesmo cliente HTTP e o mesmo modelo (openai/gpt-oss-20b); só muda o laço (docs/specs/langgraph.md). "
                 "Latência = chamadas ao LLM + ferramentas, sem as esperas do limite por minuto do plano grátis. "
                 "O modelo não é determinístico: parte da diferença em acertos pode ser variação entre execuções.", ""]
    (RAIZ / "resultados" / "motores.md").write_text("\n".join(cabecalho + corpo), encoding="utf-8")
    print("relatório: resultados/motores.md")


if __name__ == "__main__":
    main()
