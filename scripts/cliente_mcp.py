"""Faz uma pergunta pelo cliente MCP: conecta ao servidor, lista as ferramentas, chama o LLM e cita as fontes.

Uso:
  python scripts/cliente_mcp.py "quantas vezes posso trancar o curso?" --stdio
  python scripts/cliente_mcp.py "quando começam as aulas de 2026/2?" --url http://127.0.0.1:8000/mcp

--stdio sobe o servidor (python -m mcp_ufg) como subprocesso. --url usa o Streamable HTTP com o token
de MCP_TOKEN (no .env ou no ambiente; nunca na linha de comando, que fica no histórico). Precisa de
GROQ_API_KEY. O log de cada etapa sai no stderr em JSON, com o id de rastreio.
"""
import argparse
import logging
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(RAIZ / ".env")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pergunta")
    modo = parser.add_mutually_exclusive_group(required=True)
    modo.add_argument("--stdio", action="store_true")
    modo.add_argument("--url")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    import anyio
    from mcp import StdioServerParameters

    from mcp_ufg.cliente import ClienteAssistente
    from rag.llm import ClienteGroq

    if args.stdio:
        parametros = StdioServerParameters(command=sys.executable, args=["-m", "mcp_ufg"], cwd=str(RAIZ),
                                           env={**os.environ, "PYTHONPATH": str(RAIZ)})
        servidor = lambda: parametros  # noqa: E731
    else:
        token = os.environ.get("MCP_TOKEN")
        if not token:
            print("defina MCP_TOKEN no .env (crie com: python scripts/token_mcp.py criar <nome>)", file=sys.stderr)
            return 2
        from mcp.client.streamable_http import streamable_http_client
        from mcp.shared._httpx_utils import create_mcp_http_client

        def servidor():
            return streamable_http_client(args.url, http_client=create_mcp_http_client(
                headers={"Authorization": f"Bearer {token}"}))

    r = anyio.run(ClienteAssistente(servidor, ClienteGroq()).perguntar, args.pergunta)
    print(r.resposta)
    for rotulo, fonte, _ in r.citados:
        print(f"  [{rotulo}] {fonte}")
    print(f"cobertura: {r.cobertura} | ferramentas: {', '.join(c['ferramenta'] for c in r.chamadas) or 'nenhuma'} | "
          f"{r.chamadas_llm} chamadas ao LLM | {r.ms_total / 1000:.1f} s | rastreio {r.rastreio}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
