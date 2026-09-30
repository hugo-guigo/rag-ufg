"""Faz uma pergunta ao assistente (busca + LLM) e mostra a resposta com as fontes.

Uso: python scripts/perguntar.py "posso trancar a matrícula no primeiro semestre?" [--k 5]
     python scripts/perguntar.py "quando começa 2026/2?" --agente   (agente com regulamento e calendário)
"""
import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from rag.agente import Agente, FontesBanco  # noqa: E402
from rag.banco import conectar  # noqa: E402
from rag.embeddings import Embedder  # noqa: E402
from rag.llm import ClienteGroq  # noqa: E402
from rag.resposta import K_PADRAO, responder  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pergunta")
    parser.add_argument("--k", type=int, default=K_PADRAO)
    parser.add_argument("--agente", action="store_true")
    args = parser.parse_args()

    if args.agente:
        a = Agente(FontesBanco(conectar(), Embedder("int8"), k=args.k), ClienteGroq()).perguntar(args.pergunta)
        for p in a.passos:
            print(f"  {p.ferramenta}({', '.join(f'{k}={v!r}' for k, v in p.argumentos.items())})"
                  f" -> {p.erro or ', '.join(p.resultados) or 'ok'}")
        print(f"\n{a.resposta}\n")
        print(f"cobertura: {a.cobertura}")
        for fonte in a.fontes():
            print(f"fonte: {fonte}")
        print(f"\n{a.chamadas_llm} chamadas ao LLM, LLM {a.ms_llm:.0f} ms, ferramentas {a.ms_ferramentas:.0f} ms | "
              f"tokens: {a.tokens_entrada} entrada, {a.tokens_saida} saída")
        return

    r = responder(args.pergunta, conectar(), Embedder("int8"), ClienteGroq(), k=args.k)
    print(f"\n{r.resposta}\n")
    print(f"cobertura: {r.cobertura}")
    for fonte in r.fontes():
        print(f"fonte: {fonte}")
    if r.citacoes_invalidas:
        print(f"citações inválidas descartadas: {r.citacoes_invalidas}")
    print(f"\nlatência: embedding {r.ms_embedding:.0f} ms, busca {r.ms_busca:.0f} ms, LLM {r.ms_llm:.0f} ms | "
          f"tokens: {r.tokens_entrada} entrada, {r.tokens_saida} saída")
    print("trechos recuperados: " + ", ".join(x.id for x in r.recuperados))


if __name__ == "__main__":
    main()
