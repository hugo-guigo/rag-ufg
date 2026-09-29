"""Baixa o RGCG, divide pelas duas estratégias e mostra estatísticas. Grava dados/trechos/<estrategia>.jsonl.

Uso:
  python scripts/ver_trechos.py                 # estatísticas
  python scripts/ver_trechos.py rgcg-art065     # mostra um trecho pelo id
"""
import json
import statistics
import sys
from dataclasses import asdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from rag.extrair import ler_linhas  # noqa: E402
from rag.fontes import baixar, carregar_fontes  # noqa: E402
from rag.regulamento import paragrafos_rgcg  # noqa: E402
from rag.trechos import Trecho, por_artigo, por_janela  # noqa: E402


def gerar() -> dict[str, list[Trecho]]:
    rgcg = next(f for f in carregar_fontes() if f.id == "rgcg")
    paragrafos = paragrafos_rgcg(ler_linhas(baixar(rgcg)))
    return {"artigo": por_artigo(paragrafos), "janela800": por_janela(paragrafos)}


def main() -> None:
    estrategias = gerar()
    pasta = RAIZ / "dados" / "trechos"
    pasta.mkdir(parents=True, exist_ok=True)
    todos = {t.id: t for ts in estrategias.values() for t in ts}
    if len(sys.argv) > 1:
        t = todos[sys.argv[1]]
        print(f"{t.id} | artigos {list(t.artigos)} | p. {t.pagina_inicio}-{t.pagina_fim}")
        print(f"contexto: {t.contexto or '(nenhum)'}\n")
        print(t.texto)
        return
    for nome, trechos in estrategias.items():
        with open(pasta / f"{nome}.jsonl", "w", encoding="utf-8") as saida:
            for t in trechos:
                saida.write(json.dumps(asdict(t), ensure_ascii=False) + "\n")
        tamanhos = [len(t.texto) for t in trechos]
        artigos = sorted({a for t in trechos for a in t.artigos})
        print(f"{nome}: {len(trechos)} trechos | caracteres min {min(tamanhos)}, "
              f"mediana {statistics.median(tamanhos):.0f}, max {max(tamanhos)} | "
              f"artigos cobertos {len(artigos)} ({artigos[0]} a {artigos[-1]})")
        maiores = sorted(trechos, key=lambda t: len(t.texto), reverse=True)[:3]
        print("  maiores: " + ", ".join(f"{t.id} ({len(t.texto)})" for t in maiores))
    print(f"\nGravado em {pasta}")


if __name__ == "__main__":
    main()
