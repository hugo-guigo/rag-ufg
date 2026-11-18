"""Tokens do servidor MCP (endpoint /mcp da API).

Uso:
  python scripts/token_mcp.py criar <cliente>     mostra o token uma vez; guarde-o (ex.: no .env do cliente)
  python scripts/token_mcp.py listar              clientes, quando foram criados ou revogados, chamadas em 24 h
  python scripts/token_mcp.py revogar <cliente>   o token deixa de valer na próxima requisição

Usa DATABASE_URL_ADMIN do .env: o usuário app da API só pode ler a tabela de clientes.
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv  # noqa: E402

from mcp_ufg.http import criar_cliente, listar_clientes, revogar_cliente  # noqa: E402
from rag.banco import conectar  # noqa: E402


def main(argumentos: list[str]) -> int:
    load_dotenv(RAIZ / ".env")
    if not argumentos or argumentos[0] not in ("criar", "listar", "revogar"):
        print(__doc__)
        return 2
    comando, resto = argumentos[0], argumentos[1:]
    with conectar(admin=True) as conexao:
        if comando == "criar" and len(resto) == 1:
            print(criar_cliente(conexao, resto[0]))
            print(f"token do cliente {resto[0]!r} criado; ele não será mostrado de novo", file=sys.stderr)
        elif comando == "revogar" and len(resto) == 1:
            print("revogado" if revogar_cliente(conexao, resto[0]) else "cliente inexistente ou já revogado")
        elif comando == "listar":
            for cliente, criado, revogado, chamadas in listar_clientes(conexao):
                estado = f"revogado em {revogado:%d/%m/%Y %H:%M}" if revogado else "ativo"
                print(f"{cliente}\tcriado em {criado:%d/%m/%Y %H:%M}\t{estado}\t{chamadas} chamadas em 24 h")
        else:
            print(__doc__)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
