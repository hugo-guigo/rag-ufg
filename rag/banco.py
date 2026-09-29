"""Conexão com o Postgres (local ou Neon) e criação do schema e do usuário da aplicação.

Dois usuários: o admin cria tabelas e grava a ingestão; o "app" (que a API usa) só lê. Se a API for
comprometida, ela não consegue apagar nem alterar os documentos.
"""
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector
from psycopg import sql

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")


def conectar(admin: bool = False) -> psycopg.Connection:
    url = os.environ["DATABASE_URL_ADMIN" if admin else "DATABASE_URL"]
    conexao = psycopg.connect(url, autocommit=True)
    if admin:  # o tipo vector precisa existir antes de registrar o adaptador; só o admin pode criá-lo
        conexao.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(conexao)
    return conexao


def preparar(conexao: psycopg.Connection, senha_app: str) -> None:
    with conexao.transaction():
        conexao.execute((RAIZ / "db" / "schema.sql").read_text(encoding="utf-8"))
        existe = conexao.execute("SELECT 1 FROM pg_roles WHERE rolname = 'app'").fetchone()
        comando = "ALTER ROLE app WITH LOGIN PASSWORD {}" if existe else "CREATE ROLE app WITH LOGIN PASSWORD {}"
        conexao.execute(sql.SQL(comando).format(sql.Literal(senha_app)))
        banco = conexao.execute("SELECT current_database()").fetchone()[0]
        conexao.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO app").format(sql.Identifier(banco)))
        conexao.execute("GRANT USAGE ON SCHEMA public TO app")
        conexao.execute("GRANT SELECT ON documentos, trechos, eventos_calendario TO app")
