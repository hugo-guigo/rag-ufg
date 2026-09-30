"""Aplica db/schema.sql e as permissões do usuário app, sem refazer a ingestão.

Uso: python scripts/preparar_banco.py
Idempotente: rodar de novo não apaga nada. Serve para o banco local e para o Neon (etapa 7).
"""
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from rag.banco import conectar, preparar  # noqa: E402

if __name__ == "__main__":
    preparar(conectar(admin=True), os.environ["APP_DB_PASSWORD"])
    print("schema e permissões aplicados")
