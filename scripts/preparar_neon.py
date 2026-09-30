"""Prepara o banco no Neon: schema, usuário app, ingestão e a URL que a API vai usar.

Uso: python scripts/preparar_neon.py
Precisa no .env: NEON_URL_ADMIN (connection string DIRETA do neondb_owner, sem pooling).
Acrescenta ao .env, se faltarem: NEON_APP_PASSWORD (aleatória) e DATABASE_URL_NEON (usuário app pelo
pooler). Nada é impresso além de contagens.

Duas URLs de propósito: a ingestão cria tabelas e grava em lote, o que pede a conexão direta. A API
abre e fecha conexões o tempo todo, e para isso existe o pooler (PgBouncer em modo transação).
"""
import os
import secrets
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, urlparse

import psycopg
from dotenv import dotenv_values

RAIZ = Path(__file__).resolve().parent.parent
ENV = RAIZ / ".env"


def acrescentar(chave: str, valor: str) -> None:
    texto = ENV.read_text(encoding="utf-8")
    separador = "" if texto.endswith("\n") else "\n"
    with ENV.open("a", encoding="utf-8") as f:
        f.write(f"{separador}{chave}={valor}\n")


def url_do_app(url_admin: str, senha: str) -> str:
    """Mesmo endpoint, usuário app, host do pooler (ep-xxx -> ep-xxx-pooler)."""
    p = urlparse(url_admin)
    endpoint, _, resto = p.hostname.partition(".")
    host = endpoint if endpoint.endswith("-pooler") else endpoint + "-pooler"
    return f"postgresql://app:{quote(senha, safe='')}@{host}.{resto}{p.path}?sslmode=require"


def main() -> None:
    env = dotenv_values(ENV)
    admin = env.get("NEON_URL_ADMIN") or ""
    if not admin.startswith("postgres"):
        raise SystemExit("NEON_URL_ADMIN ausente no .env")
    if "-pooler" in (urlparse(admin).hostname or ""):
        raise SystemExit("NEON_URL_ADMIN deve ser a conexão direta (sem -pooler no host)")
    senha = env.get("NEON_APP_PASSWORD")
    if not senha:
        senha = secrets.token_urlsafe(24)
        acrescentar("NEON_APP_PASSWORD", senha)

    # ingerir.py cria o schema, o usuário app (com esta senha) e grava trechos e calendário
    filho = {**os.environ, "DATABASE_URL_ADMIN": admin, "APP_DB_PASSWORD": senha, "PYTHONIOENCODING": "utf-8"}
    subprocess.run([sys.executable, str(RAIZ / "scripts" / "ingerir.py")], env=filho, check=True)

    url_app = url_do_app(admin, senha)
    if env.get("DATABASE_URL_NEON") != url_app:
        if env.get("DATABASE_URL_NEON"):
            raise SystemExit("DATABASE_URL_NEON já existe no .env com outro valor; apague a linha e rode de novo")
        acrescentar("DATABASE_URL_NEON", url_app)

    with psycopg.connect(url_app, prepare_threshold=None, autocommit=True) as conexao:
        trechos = conexao.execute("SELECT count(*) FROM trechos WHERE estrategia = 'artigo_secao'").fetchone()[0]
        eventos = conexao.execute("SELECT count(*) FROM eventos_calendario WHERE embedding IS NOT NULL").fetchone()[0]
        try:
            conexao.execute("DELETE FROM trechos")
            raise SystemExit("ERRO: o usuário app conseguiu apagar trechos")
        except psycopg.errors.InsufficientPrivilege:
            pass
    print(f"Neon pronto pelo pooler, como app: {trechos} trechos artigo_secao, {eventos} eventos; app não apaga.")


if __name__ == "__main__":
    main()
