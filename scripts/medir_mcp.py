"""Mede a busca no regulamento via MCP contra a busca direta, nas 50 perguntas de avaliação.

Uso: python scripts/medir_mcp.py [--url http://127.0.0.1:8000/mcp]   (com MCP_TOKEN no ambiente para o HTTP)

Três caminhos, para cada pergunta, um depois do outro (intercalados, para uma variação da máquina no
meio da rodada pesar igual nos três):
- direto: FontesPool.buscar_regulamento no mesmo processo (embedding + SQL), o que a API faz hoje;
- stdio: a ferramenta buscar_regulamento pelo servidor MCP num subprocesso (python -m mcp_ufg);
- http: a mesma ferramenta pela API local em /mcp, com token (opcional).
Uma conexão por caminho para a rodada inteira, e uma chamada de aquecimento antes de medir.

Confere duas coisas: os ids dos trechos são os mesmos, na mesma ordem, nos três caminhos; e o recall@5
calculado como em scripts/avaliar_busca.py (perguntas com trecho anotado; acerto = o trecho anotado
está entre os 5 primeiros). Grava resultados/mcp.md e resultados/mcp.csv. Não gasta cota do Groq.
"""
import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(RAIZ / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", help="endpoint MCP da API local (usa MCP_TOKEN do ambiente)")
    args = parser.parse_args()

    import anyio

    anyio.run(medir, args.url)


async def medir(url: str | None) -> None:
    from contextlib import AsyncExitStack

    import anyio

    from mcp import Client, StdioServerParameters
    from mcp.client.streamable_http import streamable_http_client
    from mcp.shared._httpx_utils import create_mcp_http_client
    from pgvector.psycopg import register_vector
    from psycopg_pool import ConnectionPool

    from rag.agente import FontesPool
    from rag.embeddings import Embedder
    from rag.metricas import contem_trecho, percentil, posicao_do_acerto, recall_em_k, trechos_de

    perguntas = json.loads((RAIZ / "dados" / "avaliacao.json").read_text(encoding="utf-8"))
    pool = ConnectionPool(os.environ["DATABASE_URL"], min_size=1, max_size=2, open=True,
                          kwargs={"autocommit": True, "prepare_threshold": None}, configure=register_vector)
    fontes = FontesPool(pool, Embedder("int8"))

    async with AsyncExitStack() as pilha:
        caminhos = {}

        async def direto(pergunta: str) -> list[str]:
            return [r.id for r in await anyio.to_thread.run_sync(fontes.buscar_regulamento, pergunta, 5)]
        caminhos["direto"] = direto

        def via(cliente):
            async def chamar(pergunta: str) -> list[str]:
                r = await cliente.call_tool("buscar_regulamento", {"pergunta": pergunta, "k": 5})
                if r.is_error:
                    raise RuntimeError(r.content[0].text)
                return [t["id"] for t in r.structured_content["trechos"]]
            return chamar

        stdio = StdioServerParameters(command=sys.executable, args=["-m", "mcp_ufg"], cwd=str(RAIZ),
                                      env={**os.environ, "PYTHONPATH": str(RAIZ)})
        caminhos["stdio"] = via(await pilha.enter_async_context(Client(stdio)))
        if url:
            http = create_mcp_http_client(headers={"Authorization": f"Bearer {os.environ['MCP_TOKEN']}"})
            caminhos["http"] = via(await pilha.enter_async_context(Client(streamable_http_client(url, http_client=http))))

        for chamar in caminhos.values():  # aquecimento: primeira inferência do ONNX e primeira conexão do pool
            await chamar("aquecimento")

        ms = {nome: [] for nome in caminhos}
        ids = {nome: {} for nome in caminhos}
        for p in perguntas:
            for nome, chamar in caminhos.items():
                inicio = time.perf_counter()
                ids[nome][p["id"]] = await chamar(p["pergunta"])
                ms[nome].append(1000 * (time.perf_counter() - inicio))
    pool.close()

    com_trecho = [p for p in perguntas if "trecho" in p]
    textos = dict(pool_textos())
    recall = {}
    for nome in caminhos:
        posicoes = [posicao_do_acerto(ids[nome][p["id"]],
                                      lambda i: any(contem_trecho(textos[i], t) for t in trechos_de(p)))
                    for p in com_trecho]
        recall[nome] = recall_em_k(posicoes, 5)
    iguais = {nome: sum(ids[nome][p["id"]] == ids["direto"][p["id"]] for p in perguntas) for nome in caminhos}

    saida = RAIZ / "resultados"
    with open(saida / "mcp.csv", "w", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        escritor.writerow(["id", *[f"ms_{n}" for n in caminhos], *[f"iguais_{n}" for n in caminhos if n != "direto"]])
        for i, p in enumerate(perguntas):
            escritor.writerow([p["id"], *[f"{ms[n][i]:.2f}" for n in caminhos],
                               *[int(ids[n][p["id"]] == ids["direto"][p["id"]]) for n in caminhos if n != "direto"]])

    def fmt(x: float) -> str:
        return f"{x:.1f}".replace(".", ",")

    nomes = {"direto": "Direto (mesmo processo)", "stdio": "MCP em stdio", "http": "MCP em HTTP local"}
    linhas = [
        "# Busca no regulamento via MCP x busca direta",
        "",
        f"Gerado por `scripts/medir_mcp.py` em {time.strftime('%d/%m/%Y')}. 50 perguntas de avaliação, cada uma "
        "pelos caminhos em sequência; uma conexão por caminho e uma chamada de aquecimento antes. Máquina: a "
        "mesma do resto do projeto (i3 de 4 núcleos, Windows, Postgres em Docker local).",
        "",
        "| Caminho | p50 (ms) | p95 (ms) | Mesmos trechos e ordem da busca direta | Recall@5 (perguntas com trecho) |",
        "| --- | --- | --- | --- | --- |",
    ]
    for nome in caminhos:
        linhas.append(f"| {nomes[nome]} | {fmt(percentil(ms[nome], 0.5))} | {fmt(percentil(ms[nome], 0.95))} | "
                      f"{iguais[nome]}/{len(perguntas)} | {recall[nome] * 100:.0f}% ({len(com_trecho)} perguntas) |")
    linhas += ["", "A latência do direto é a do embedding da pergunta mais o SQL. Os caminhos MCP somam a "
               "serialização JSON-RPC e a passagem entre processos (stdio) ou pela pilha HTTP local (http). "
               "No HTTP entram também, a cada chamada, a conferência do token e a contagem do limite (duas "
               "consultas ao banco) e a gravação do rastreio. Medido com o banco no Docker da mesma máquina; "
               "com o Neon, cada consulta ao banco atravessa a rede.", ""]
    (saida / "mcp.md").write_text("\n".join(linhas), encoding="utf-8")
    print("\n".join(linhas))


def pool_textos():
    """id -> texto dos trechos da estratégia usada, para conferir o trecho anotado (como avaliar_busca)."""
    import psycopg

    with psycopg.connect(os.environ["DATABASE_URL"]) as conexao:
        return conexao.execute("SELECT id, texto FROM trechos WHERE estrategia = 'artigo_secao' "
                               "AND modelo = 'multilingual-e5-small-int8'").fetchall()


if __name__ == "__main__":
    main()
