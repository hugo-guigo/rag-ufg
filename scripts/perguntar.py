"""Faz uma pergunta ao assistente (busca + LLM) e mostra a resposta com as fontes.

Uso: python scripts/perguntar.py "posso trancar a matrícula no primeiro semestre?" [--k 5]
"""
import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from rag.banco import conectar  # noqa: E402
from rag.embeddings import Embedder  # noqa: E402
from rag.llm import ClienteGroq  # noqa: E402
from rag.resposta import K_PADRAO, responder  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pergunta")
    parser.add_argument("--k", type=int, default=K_PADRAO)
    args = parser.parse_args()

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
