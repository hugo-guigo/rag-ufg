"""Cria o .env local com senhas aleatórias. Não sobrescreve um .env existente.

A chave do Groq não é gerada: cole a sua no .env (GROQ_API_KEY=...) quando chegar a etapa do LLM.
"""
import secrets
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ENV = RAIZ / ".env"

if ENV.exists():
    print(".env já existe; nada foi alterado.")
else:
    admin, app = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    ENV.write_text(
        f"POSTGRES_ADMIN_PASSWORD={admin}\n"
        f"APP_DB_PASSWORD={app}\n"
        f"DATABASE_URL_ADMIN=postgresql://admin:{admin}@127.0.0.1:5433/rag\n"
        f"DATABASE_URL=postgresql://app:{app}@127.0.0.1:5433/rag\n"
        "GROQ_API_KEY=\n",
        encoding="utf-8",
    )
    print(f".env criado em {ENV}")
