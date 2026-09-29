"""Busca os trechos mais parecidos com uma pergunta (sem LLM ainda).

Uso: python scripts/buscar.py "posso trancar a matrícula no primeiro semestre?" [--k 5] [--estrategia janela800]
"""
import argparse
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from rag.banco import conectar  # noqa: E402
from rag.busca import buscar  # noqa: E402
from rag.embeddings import Embedder  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pergunta")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--estrategia", default="artigo_secao")
    parser.add_argument("--variante", choices=["int8", "fp32"], default="int8")
    args = parser.parse_args()

    embedder = Embedder(args.variante)
    conexao = conectar()
    t0 = time.perf_counter()
    vetor = embedder.pergunta(args.pergunta)
    t1 = time.perf_counter()
    resultados = buscar(conexao, vetor, args.k, args.estrategia, embedder.nome)
    t2 = time.perf_counter()
    print(f"embedding da pergunta {1000 * (t1 - t0):.0f} ms | busca no banco {1000 * (t2 - t1):.0f} ms\n")
    for r in resultados:
        print(f"{r.similaridade:.3f}  {r.id}  artigos {list(r.artigos)}  p. {r.pagina_inicio}")
        print(f"       {r.texto[:160].replace(chr(10), ' ')}...\n")


if __name__ == "__main__":
    main()
