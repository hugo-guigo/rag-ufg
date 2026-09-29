"""Sorteia respostas julgadas pelo LLM para revisão humana e mede a concordância com o juiz.

Uso:
  python scripts/amostra_revisao.py            # cria resultados/revisao_juiz.csv (se não existir)
  python scripts/amostra_revisao.py --medir    # compara as colunas preenchidas à mão com o juiz

Preencha hugo_correta (sim/parcial/nao) e hugo_fiel (sim/nao) olhando o PDF do RGCG.
"""
import argparse
import csv
import json
import random
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ORIGEM = RAIZ / "resultados" / "respostas" / "avaliacao_k5.jsonl"
REVISAO = RAIZ / "resultados" / "revisao_juiz.csv"
SEMENTE, TAMANHO = 2026, 10
CAMPOS = ["id", "pergunta", "referencia", "resposta", "citados", "juiz_correta", "juiz_fiel", "hugo_correta", "hugo_fiel"]


def criar() -> None:
    if REVISAO.exists():
        print(f"{REVISAO.name} já existe; não sobrescrevo a revisão.")
        return
    registros = [json.loads(linha) for linha in ORIGEM.open(encoding="utf-8")]
    amostra = sorted(random.Random(SEMENTE).sample(registros, TAMANHO), key=lambda r: r["id"])
    with REVISAO.open("w", encoding="utf-8", newline="") as saida:
        escritor = csv.DictWriter(saida, fieldnames=CAMPOS)
        escritor.writeheader()
        for r in amostra:
            escritor.writerow({"id": r["id"], "pergunta": r["pergunta"], "referencia": r["referencia"],
                               "resposta": r["resposta"], "citados": " ".join(r["citados"]),
                               "juiz_correta": r["correta"], "juiz_fiel": "sim" if r["fiel"] else "nao",
                               "hugo_correta": "", "hugo_fiel": ""})
    print(f"amostra de {TAMANHO} em {REVISAO}: {', '.join(r['id'] for r in amostra)}")


def medir() -> None:
    linhas = [r for r in csv.DictReader(REVISAO.open(encoding="utf-8")) if r["hugo_correta"] and r["hugo_fiel"]]
    if not linhas:
        print("nenhuma linha revisada ainda")
        return
    correta = sum(r["hugo_correta"] == r["juiz_correta"] for r in linhas)
    fiel = sum(r["hugo_fiel"] == r["juiz_fiel"] for r in linhas)
    print(f"concordância em 'correta': {correta}/{len(linhas)} | em 'fiel': {fiel}/{len(linhas)}")
    for r in linhas:
        if r["hugo_correta"] != r["juiz_correta"] or r["hugo_fiel"] != r["juiz_fiel"]:
            print(f"  {r['id']}: juiz {r['juiz_correta']}/{r['juiz_fiel']}, Hugo {r['hugo_correta']}/{r['hugo_fiel']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--medir", action="store_true")
    medir() if parser.parse_args().medir else criar()
