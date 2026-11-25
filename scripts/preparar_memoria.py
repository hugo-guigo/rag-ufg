"""Cria as tabelas da memória das conversas (motor langgraph) e dá ao usuário app só o que ele usa.

Uso: python scripts/preparar_memoria.py   (usa DATABASE_URL_ADMIN; serve para o banco local e o Neon)
Idempotente: rodar de novo não apaga nada. Rodar depois de scripts/preparar_banco.py, que cria o usuário app.
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from rag.banco import conectar  # noqa: E402
from rag.memoria import TABELAS_DO_APP, preparar_memoria  # noqa: E402

if __name__ == "__main__":
    with conectar(admin=True) as conexao:
        preparar_memoria(conexao)
    print(f"memória pronta: {', '.join(TABELAS_DO_APP)} com SELECT, INSERT, UPDATE e DELETE para o app")
