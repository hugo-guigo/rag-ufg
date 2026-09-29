"""Avalia só a busca (sem LLM): recall@k e MRR por estratégia de chunking e por modelo de embedding.

Uso: python scripts/avaliar_busca.py [--conjunto avaliacao|teste]
  avaliacao (padrão): 50 perguntas usadas para escolher a configuração.
  teste: 10 perguntas do Hugo, rodadas uma vez no fim, só na configuração escolhida.
Pré-requisito: python scripts/ingerir.py --variante int8  e  --variante fp32
Saída: resultados/busca[_teste].md e .csv

Critério principal de acerto: o trecho devolvido CONTÉM o trecho-chave anotado (a frase com a resposta).
Critério secundário: o trecho devolvido pertence a um dos artigos anotados. O secundário favorece
janelas, que cobrem dois ou três artigos cada, por isso o principal é o outro.
"""
import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from rag.banco import conectar  # noqa: E402
from rag.busca import buscar  # noqa: E402
from rag.embeddings import Embedder  # noqa: E402
from rag.metricas import (contem_trecho, melhor_limiar, mrr, percentil, posicao_do_acerto,  # noqa: E402
                          recall_em_k, trechos_de)

KS = [1, 3, 5, 10]
ESTRATEGIAS = ["artigo", "artigo_secao", "artigo_sem_contexto", "janela800", "janela400"]
VARIANTES = ["int8", "fp32"]
# O fp32 só entra na busca vetorial: ele serve para medir o custo da quantização, não para escolher o modo.
MODOS_POR_VARIANTE = {"int8": ["vetor", "texto", "hibrida"], "fp32": ["vetor"]}
# Escolhida no conjunto de avaliação (ver resultados/busca.md). O conjunto de teste roda só nela.
ESCOLHIDA = ("artigo_secao", "vetor")
SAIDA = RAIZ / "resultados"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--conjunto", choices=["avaliacao", "teste"], default="avaliacao")
    args = parser.parse_args()
    teste = args.conjunto == "teste"
    sufixo = "_teste" if teste else ""
    perguntas = json.loads((RAIZ / "dados" / f"{args.conjunto}.json").read_text(encoding="utf-8"))
    com_trecho = [p for p in perguntas if "trecho" in p]  # regulamento + misto
    sem_resposta = [p for p in perguntas if p["tipo"] == "sem_resposta"]
    conexao = conectar()
    SAIDA.mkdir(exist_ok=True)

    linhas_csv, resumo = [], []
    for variante in (["int8"] if teste else VARIANTES):
        embedder = Embedder(variante)
        existentes = conexao.execute("SELECT count(*) FROM trechos WHERE modelo = %s", (embedder.nome,)).fetchone()[0]
        if not existentes:
            print(f"pulando {embedder.nome}: rode scripts/ingerir.py --variante {variante}")
            continue
        embedder.pergunta("aquecimento")  # a primeira chamada do onnxruntime é mais lenta
        vetores, ms_embedding = {}, []
        for p in com_trecho + sem_resposta:
            t0 = time.perf_counter()
            vetores[p["id"]] = embedder.pergunta(p["pergunta"])
            ms_embedding.append(1000 * (time.perf_counter() - t0))

        configuracoes = [(e, m) for m in MODOS_POR_VARIANTE[variante] for e in ESTRATEGIAS]
        if teste:
            configuracoes = [ESCOLHIDA]
        for estrategia, modo in configuracoes:
            pos_trecho, pos_artigo, ms_busca, top1_com, top1_sem = [], [], [], [], []
            for p in com_trecho + sem_resposta:
                t0 = time.perf_counter()
                res = buscar(conexao, vetores[p["id"]], max(KS), estrategia, embedder.nome, modo, p["pergunta"])
                ms_busca.append(1000 * (time.perf_counter() - t0))
                if p["tipo"] == "sem_resposta":
                    top1_sem.append(res[0].similaridade if res else 0.0)
                    continue
                top1_com.append(res[0].similaridade if res else 0.0)
                pt = posicao_do_acerto(res, lambda r: any(contem_trecho(r.texto, t) for t in trechos_de(p)))
                pa = posicao_do_acerto(res, lambda r: bool(set(r.artigos) & set(p["artigos"])))
                pos_trecho.append(pt)
                pos_artigo.append(pa)
                linhas_csv.append({"modelo": embedder.nome, "estrategia": estrategia, "modo": modo, "id": p["id"],
                                   "pergunta": p["pergunta"], "posicao_trecho": pt or "", "posicao_artigo": pa or "",
                                   "top1_id": res[0].id if res else "", "top1_similaridade": f"{res[0].similaridade:.4f}" if res else ""})
            tamanhos = conexao.execute(
                "SELECT avg(length(texto)), avg(cardinality(artigos)), count(*) FROM trechos "
                "WHERE estrategia = %s AND modelo = %s", (estrategia, embedder.nome)).fetchone()
            limiar, acuracia = melhor_limiar(top1_com, top1_sem)
            resumo.append({
                "modelo": embedder.nome, "estrategia": estrategia, "modo": modo, "trechos": tamanhos[2],
                "chars": float(tamanhos[0]), "artigos_por_trecho": float(tamanhos[1]),
                **{f"r@{k}": recall_em_k(pos_trecho, k) for k in KS},
                "mrr@10": mrr(pos_trecho, 10), "r@5_artigo": recall_em_k(pos_artigo, 5),
                "sim_com": (min(top1_com), statistics.median(top1_com), max(top1_com)),
                "sim_sem": (min(top1_sem), statistics.median(top1_sem), max(top1_sem)),
                "limiar": limiar, "acuracia_limiar": acuracia,
                "busca_p50": percentil(ms_busca, 0.5), "busca_p95": percentil(ms_busca, 0.95),
                "emb_p50": percentil(ms_embedding, 0.5), "emb_p95": percentil(ms_embedding, 0.95),
                "falhas_r5": [p["id"] for p, pt in zip(com_trecho, pos_trecho) if not pt or pt > 5],
            })
            print(f"{embedder.nome:32} {estrategia:20} {modo:8} r@1 {resumo[-1]['r@1']:.2f} r@5 {resumo[-1]['r@5']:.2f} "
                  f"mrr {resumo[-1]['mrr@10']:.2f}")

    with open(SAIDA / f"busca{sufixo}.csv", "w", encoding="utf-8", newline="") as saida:
        escritor = csv.DictWriter(saida, fieldnames=list(linhas_csv[0]))
        escritor.writeheader()
        escritor.writerows(linhas_csv)
    pareadas = comparacoes_pareadas(linhas_csv)
    (SAIDA / f"busca{sufixo}.md").write_text(relatorio(resumo, pareadas, len(com_trecho), len(sem_resposta), args.conjunto),
                                    encoding="utf-8")
    print(f"\nGravado em {SAIDA}")


# Cada par muda uma coisa só. (variante, estratégia, modo)
PARES = [
    (("int8", "artigo", "vetor"), ("int8", "artigo_secao", "vetor"), "contexto completo vs só a seção"),
    (("int8", "artigo_secao", "vetor"), ("int8", "artigo_sem_contexto", "vetor"), "só a seção vs sem contexto"),
    (("int8", "artigo_secao", "vetor"), ("int8", "janela800", "vetor"), "por artigo vs janela de 800"),
    (("int8", "janela800", "vetor"), ("int8", "janela400", "vetor"), "janela de 800 vs janela de 400"),
    (("int8", "artigo_secao", "vetor"), ("int8", "artigo_secao", "hibrida"), "vetorial vs híbrida"),
    (("int8", "artigo_secao", "vetor"), ("fp32", "artigo_secao", "vetor"), "int8 vs fp32"),
]


def comparacoes_pareadas(linhas_csv: list[dict], k: int = 5) -> list[str]:
    """Em quantas perguntas só a configuração A acerta no top k, e em quantas só a B.

    Com 34 perguntas, cada uma vale 3 pontos percentuais; a contagem pareada mostra se a diferença
    vem de muitas perguntas ou de uma ou duas.
    """
    pos: dict[tuple, dict[str, int]] = {}
    for r in linhas_csv:
        chave = (r["modelo"].rsplit("-", 1)[-1], r["estrategia"], r["modo"])
        pos.setdefault(chave, {})[r["id"]] = int(r["posicao_trecho"]) if r["posicao_trecho"] else 10 ** 6
    saida = []
    for a, b, nome in PARES:
        if a not in pos or b not in pos:
            continue
        so_a = [i for i in pos[a] if pos[a][i] <= k < pos[b][i]]
        so_b = [i for i in pos[a] if pos[b][i] <= k < pos[a][i]]
        saida.append(f"| {nome} | {len(so_a)} ({', '.join(so_a) or '-'}) | {len(so_b)} ({', '.join(so_b) or '-'}) |")
    return saida


def relatorio(resumo: list[dict], pareadas: list[str], n_com: int, n_sem: int, conjunto: str) -> str:
    def pct(x: float) -> str:
        return f"{100 * x:.0f}%"

    linhas = [
        f"# Avaliação da busca (sem LLM), conjunto {conjunto}",
        "",
        f"{n_com} perguntas com resposta no regulamento e {n_sem} sem resposta.",
        "Acerto = o trecho devolvido contém a frase anotada com a resposta. Gerado por scripts/avaliar_busca.py.",
        "",
        "| Modelo | Estratégia | Busca | Trechos | Caracteres (média) | Artigos por trecho | R@1 | R@3 | R@5 | R@10 | MRR@10 | R@5 (critério artigo) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in resumo:
        linhas.append(f"| {r['modelo']} | {r['estrategia']} | {r['modo']} | {r['trechos']} | {r['chars']:.0f} | "
                      f"{r['artigos_por_trecho']:.1f} | {pct(r['r@1'])} | {pct(r['r@3'])} | {pct(r['r@5'])} | "
                      f"{pct(r['r@10'])} | {r['mrr@10']:.2f} | {pct(r['r@5_artigo'])} |")
    linhas += [
        "",
        "## Comparações pareadas (acerto no top 5)",
        "",
        "| Comparação (A vs B) | Só A acerta | Só B acerta |",
        "|---|---|---|",
        *pareadas,
    ]
    linhas += [
        "",
        "## A similaridade do 1º resultado separa \"tem resposta\" de \"não sei\"?",
        "",
        "| Modelo | Estratégia | Busca | Com resposta (mín / mediana / máx) | Sem resposta (mín / mediana / máx) | Melhor limiar | Acurácia com ele |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in resumo:
        com, sem = r["sim_com"], r["sim_sem"]
        linhas.append(f"| {r['modelo']} | {r['estrategia']} | {r['modo']} | {com[0]:.3f} / {com[1]:.3f} / {com[2]:.3f} | "
                      f"{sem[0]:.3f} / {sem[1]:.3f} / {sem[2]:.3f} | {r['limiar']:.3f} | {pct(r['acuracia_limiar'])} |")
    linhas += [
        "",
        "O limiar foi escolhido olhando as próprias perguntas, então a acurácia dele é otimista.",
        "",
        "## Latência (ms, CPU local)",
        "",
        "| Modelo | Estratégia | Busca | Embedding da pergunta p50 / p95 | Busca no banco p50 / p95 |",
        "|---|---|---|---|---|",
    ]
    for r in resumo:
        linhas.append(f"| {r['modelo']} | {r['estrategia']} | {r['modo']} | {r['emb_p50']:.0f} / {r['emb_p95']:.0f} | "
                      f"{r['busca_p50']:.1f} / {r['busca_p95']:.1f} |")
    linhas += ["", "## Perguntas sem acerto no top 5", ""]
    for r in resumo:
        linhas.append(f"- {r['modelo']} / {r['estrategia']} / {r['modo']}: {', '.join(r['falhas_r5']) or 'nenhuma'}")
    return "\n".join(linhas) + "\n"


if __name__ == "__main__":
    main()
