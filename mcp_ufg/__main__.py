"""Servidor MCP em stdio, para uso local: python -m mcp_ufg

Lê DATABASE_URL do ambiente ou do .env na raiz do projeto (o mesmo banco da API, local ou Neon).
No stdio o stdout é o canal do protocolo: todo log vai para o stderr, em JSON, uma linha por evento.
"""
import logging
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def montar_acervo():
    import os

    from dotenv import load_dotenv
    from pgvector.psycopg import register_vector
    from psycopg_pool import ConnectionPool

    from mcp_ufg.ferramentas import AcervoPool
    from rag.agente import FontesPool
    from rag.embeddings import Embedder

    load_dotenv(RAIZ / ".env")
    pool = ConnectionPool(os.environ["DATABASE_URL"], min_size=1, max_size=2, open=True,
                          kwargs={"autocommit": True, "prepare_threshold": None}, configure=register_vector)
    embedder = Embedder("int8")
    embedder.pergunta("aquecimento")  # a primeira inferência do ONNX é a mais lenta
    return AcervoPool(FontesPool(pool, embedder), pool), pool


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # uma linha por requisição HTTP poluiria o rastreio
    from mcp_ufg.rastreio import Rastreio
    from mcp_ufg.servidor import criar_servidor

    acervo, pool = montar_acervo()
    try:
        criar_servidor(acervo, middleware=[Rastreio()]).run("stdio")
    finally:
        pool.close()


if __name__ == "__main__":
    main()
