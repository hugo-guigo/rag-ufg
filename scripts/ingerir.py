"""Ingestão completa: schema, documentos, trechos com embedding e calendário.

Uso: python scripts/ingerir.py [--variante int8|fp32]
Idempotente: apaga e regrava os trechos da variante numa transação, então rodar de novo não duplica.
"""
import argparse
import os
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from rag.banco import conectar, preparar  # noqa: E402
from rag.calendario import ler_csv  # noqa: E402
from rag.embeddings import Embedder  # noqa: E402
from rag.extrair import ler_linhas  # noqa: E402
from rag.fontes import baixar, carregar_fontes  # noqa: E402
from rag.regulamento import paragrafos_rgcg  # noqa: E402
from rag.trechos import por_artigo, por_janela  # noqa: E402

CALENDARIO_CSV = RAIZ / "dados" / "calendario_2026.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variante", choices=["int8", "fp32"], default="int8")
    args = parser.parse_args()

    fontes = {f.id: f for f in carregar_fontes()}
    for f in fontes.values():
        baixar(f)
    paragrafos = paragrafos_rgcg(ler_linhas(fontes["rgcg"].caminho))
    trechos = (por_artigo(paragrafos, contexto="completo") + por_artigo(paragrafos, contexto="secao")
               + por_artigo(paragrafos, contexto="nenhum")
               + por_janela(paragrafos, tamanho=800, sobreposicao=150)
               + por_janela(paragrafos, tamanho=400, sobreposicao=80))

    t0 = time.perf_counter()
    embedder = Embedder(args.variante)
    print(f"modelo {embedder.nome} carregado em {time.perf_counter() - t0:.1f} s")
    vetores = embedder.documentos([t.texto_para_embedding() for t in trechos])
    e = embedder.estatisticas
    print(f"{e.textos} trechos em {e.segundos:.1f} s ({1000 * e.segundos / e.textos:.0f} ms/trecho), "
          f"{e.truncados} truncados em 512 tokens")

    conexao = conectar(admin=True)
    preparar(conexao, os.environ["APP_DB_PASSWORD"])
    with conexao.transaction():
        for f in fontes.values():
            conexao.execute(
                """INSERT INTO documentos (id, titulo, url, sha256) VALUES (%s, %s, %s, %s)
                   ON CONFLICT (id) DO UPDATE SET titulo = EXCLUDED.titulo, url = EXCLUDED.url,
                   sha256 = EXCLUDED.sha256""",
                (f.id, f.titulo, f.url, f.sha256))
        conexao.execute("DELETE FROM trechos WHERE modelo = %s", (embedder.nome,))
        with conexao.cursor() as cur:
            cur.executemany(
                """INSERT INTO trechos (id, estrategia, modelo, documento, texto, contexto, artigos,
                   pagina_inicio, pagina_fim, embedding) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                [(t.id, t.estrategia, embedder.nome, t.documento, t.texto, t.contexto, list(t.artigos),
                  t.pagina_inicio, t.pagina_fim, v) for t, v in zip(trechos, vetores)])
        eventos = ler_csv(CALENDARIO_CSV)
        conexao.execute("DELETE FROM eventos_calendario")
        with conexao.cursor() as cur:
            cur.executemany(
                """INSERT INTO eventos_calendario (documento, data_inicio, data_fim, descricao, categoria, pagina)
                   VALUES ('calendario-2026', %s, %s, %s, %s, %s)""",
                [(ev.data_inicio, ev.data_fim, ev.descricao, ev.categoria, ev.pagina) for ev in eventos])
    for estrategia, n in conexao.execute(
            "SELECT estrategia, count(*) FROM trechos WHERE modelo = %s GROUP BY 1 ORDER BY 1", (embedder.nome,)):
        print(f"  {estrategia}: {n} trechos")
    print(f"  calendário: {len(eventos)} eventos")


if __name__ == "__main__":
    main()
