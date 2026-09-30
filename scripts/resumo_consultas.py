"""Mostra o resumo do log da API (db/resumo.sql) e os erros mais recentes.

Uso: python scripts/resumo_consultas.py [--dias 7]
"""
import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from rag.banco import conectar  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dias", type=int, default=7)
    args = parser.parse_args()
    conexao = conectar()
    cursor = conexao.execute((RAIZ / "db" / "resumo.sql").read_text(encoding="utf-8"), {"dias": args.dias})
    colunas = [c.name for c in cursor.description]
    linhas = cursor.fetchall()
    if not linhas:
        print(f"nenhuma consulta nos últimos {args.dias} dias")
        return
    largura = max(len(c) for c in colunas)
    for linha in linhas:
        for coluna, valor in zip(colunas, linha):
            print(f"{coluna:<{largura}}  {valor if valor is not None else '-'}")
        print()
    erros = conexao.execute(
        """SELECT criado_em, status, left(erro, 120) FROM consultas
           WHERE erro IS NOT NULL AND criado_em > now() - make_interval(days => %s)
           ORDER BY criado_em DESC LIMIT 5""", (args.dias,)).fetchall()
    if erros:
        print("últimos erros:")
        for quando, status, erro in erros:
            print(f"  {quando:%Y-%m-%d %H:%M} {status} {erro}")


if __name__ == "__main__":
    main()
