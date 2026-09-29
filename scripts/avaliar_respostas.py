"""Avalia as respostas do RAG (busca + LLM) com o juiz. Gasta cota do Groq: ~3 mil tokens por pergunta.

Uso: python scripts/avaliar_respostas.py --k 5 [--conjunto avaliacao|teste] [--limite N]
Retoma de onde parou: cada pergunta respondida e julgada fica em resultados/respostas/<conjunto>_k<k>.jsonl.
Relatório (todas as configurações já rodadas): resultados/respostas[_teste].md e .csv

Métricas:
- correta (juiz): a resposta traz o essencial da referência humana.
- fiel (juiz): toda afirmação está nos trechos citados. Só conta respostas com cobertura total ou parcial.
- "não sei" correto: pergunta sem resposta com cobertura "nenhuma" (estrito) ou "nenhuma"/"parcial" (tolerante).
- falso "não sei": pergunta com resposta que recebeu cobertura "nenhuma".
- citação correta (determinística): algum trecho citado contém a frase anotada com a resposta.
- latência sem as esperas de ritmo do plano grátis; custo com os preços pagos do Groq.
"""
import argparse
import csv
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from rag.banco import conectar  # noqa: E402
from rag.embeddings import Embedder  # noqa: E402
from rag.juiz import REFERENCIA_SEM_RESPOSTA, julgar  # noqa: E402
from rag.llm import ClienteGroq, ErroLLM  # noqa: E402
from rag.metricas import contem_trecho, percentil, trechos_de  # noqa: E402
from rag.resposta import responder, rotulo  # noqa: E402

PASTA = RAIZ / "resultados" / "respostas"
# US$ por milhão de tokens, groq.com/pricing (consultado em 29/09/2026). O plano grátis não cobra;
# o custo mostra quanto sairia no plano pago.
PRECO = {"openai/gpt-oss-20b": (0.075, 0.30), "openai/gpt-oss-120b": (0.15, 0.60)}


def custo(modelo: str, entrada: float, saida: float) -> float:
    pe, ps = PRECO[modelo]
    return (entrada * pe + saida * ps) / 1e6


def rodar(conjunto: str, k: int, limite: int | None) -> None:
    perguntas = [p for p in json.loads((RAIZ / "dados" / f"{conjunto}.json").read_text(encoding="utf-8"))
                 if p["tipo"] in ("regulamento", "sem_resposta")]
    PASTA.mkdir(parents=True, exist_ok=True)
    arquivo = PASTA / f"{conjunto}_k{k}.jsonl"
    feitos = {json.loads(linha)["id"] for linha in arquivo.open(encoding="utf-8")} if arquivo.exists() else set()
    pendentes = [p for p in perguntas if p["id"] not in feitos][:limite]
    print(f"{conjunto} k={k}: {len(feitos)} já feitas, {len(pendentes)} agora")
    if not pendentes:
        return
    conexao, embedder, cliente = conectar(), Embedder("int8"), ClienteGroq()
    embedder.pergunta("aquecimento")
    for p in pendentes:
        antes = cliente.limites_dobrados
        try:
            r = responder(p["pergunta"], conexao, embedder, cliente, k=k)
            referencia = p.get("resposta", REFERENCIA_SEM_RESPOSTA)
            j = julgar(cliente, p["pergunta"], referencia, r.resposta, [(rotulo(c), c.texto) for c in r.citados])
        except ErroLLM as erro:
            print(f"  {p['id']}: parei ({erro}). Rode de novo para continuar.")
            return
        trechos = trechos_de(p)
        registro = {
            "id": p["id"], "tipo": p["tipo"], "parcial_anotado": p.get("parcial", False), "pergunta": p["pergunta"],
            "referencia": referencia, "resposta": r.resposta, "cobertura": r.cobertura,
            "citados": [c.id for c in r.citados], "recuperados": [c.id for c in r.recuperados],
            "citacoes_invalidas": r.citacoes_invalidas,
            "citacao_correta": any(contem_trecho(c.texto, t) for c in r.citados for t in trechos) if trechos else None,
            "recuperou_trecho": any(contem_trecho(c.texto, t) for c in r.recuperados for t in trechos) if trechos else None,
            "correta": j.conteudo["correta"], "fiel": j.conteudo["fiel"], "sem_suporte": j.conteudo["sem_suporte"],
            "justificativa": j.conteudo["justificativa"],
            "ms_embedding": r.ms_embedding, "ms_busca": r.ms_busca, "ms_llm": r.ms_llm, "ms_llm_total": r.ms_llm_total,
            "tokens_entrada": r.tokens_entrada, "tokens_saida": r.tokens_saida, "tentativas_llm": r.tentativas_llm,
            "modelo": r.modelo, "limites_dobrados": cliente.limites_dobrados - antes, "juiz_tokens_entrada": j.tokens_entrada, "juiz_tokens_saida": j.tokens_saida,
        }
        with arquivo.open("a", encoding="utf-8") as saida:
            saida.write(json.dumps(registro, ensure_ascii=False) + "\n")
        print(f"  {p['id']:4} {r.cobertura:8} correta={registro['correta']:7} fiel={registro['fiel']!s:5} "
              f"llm {r.ms_llm:.0f} ms")


def pct(n: int, total: int) -> str:
    return f"{n}/{total} ({100 * n / total:.0f}%)" if total else "-"


def relatorio(conjunto: str) -> None:
    sufixo = "_teste" if conjunto == "teste" else ""
    arquivos = sorted(PASTA.glob(f"{conjunto}_k*.jsonl"), key=lambda a: int(a.stem.rsplit("_k", 1)[1]))
    if not arquivos:
        return
    linhas = [f"# Avaliação das respostas (busca + LLM), conjunto {conjunto}", "",
              "Gerado por scripts/avaliar_respostas.py. Modelo das respostas: openai/gpt-oss-20b. "
              "Juiz: openai/gpt-oss-120b. Busca: artigo com seção, vetorial, e5-small int8.", ""]
    tabela = ["| Métrica | " + " | ".join(f"k={a.stem.rsplit('_k', 1)[1]}" for a in arquivos) + " |",
              "|---|" + "---|" * len(arquivos)]
    colunas, todos = [], []
    for a in arquivos:
        regs = [json.loads(linha) for linha in a.open(encoding="utf-8")]
        todos += [{"k": a.stem.rsplit("_k", 1)[1], **r} for r in regs]
        com = [r for r in regs if r["tipo"] == "regulamento"]
        sem = [r for r in regs if r["tipo"] == "sem_resposta"]
        afirmam = [r for r in regs if r["cobertura"] != "nenhuma"]
        ms = [r["ms_embedding"] + r["ms_busca"] + r["ms_llm"] for r in regs]
        ent = statistics.mean(r["tokens_entrada"] for r in regs)
        sai = statistics.mean(r["tokens_saida"] for r in regs)
        c = custo(regs[0]["modelo"], ent, sai)
        colunas.append({
            "Perguntas (com resposta / sem)": f"{len(com)} / {len(sem)}",
            "Trecho certo entre os recuperados": pct(sum(bool(r["recuperou_trecho"]) for r in com), len(com)),
            "Correta, com resposta (juiz: sim)": pct(sum(r["correta"] == "sim" for r in com), len(com)),
            "Correta ou parcial, com resposta": pct(sum(r["correta"] != "nao" for r in com), len(com)),
            "Citação correta (trecho anotado citado)": pct(sum(bool(r["citacao_correta"]) for r in com), len(com)),
            "Fiel às fontes citadas (juiz)": pct(sum(r["fiel"] for r in afirmam), len(afirmam)),
            "\"Não sei\" correto, estrito (cobertura nenhuma)": pct(sum(r["cobertura"] == "nenhuma" for r in sem), len(sem)),
            "\"Não sei\" correto, tolerante (nenhuma ou parcial)": pct(sum(r["cobertura"] != "total" for r in sem), len(sem)),
            "Sem resposta julgadas corretas (juiz)": pct(sum(r["correta"] == "sim" for r in sem), len(sem)),
            "Falso \"não sei\" (tinha resposta)": pct(sum(r["cobertura"] == "nenhuma" for r in com), len(com)),
            "Citações inválidas": str(sum(r["citacoes_invalidas"] for r in regs)),
            "Chamadas refeitas por JSON cortado": str(sum(r.get("limites_dobrados", 0) for r in regs)),
            "Latência p50 / p95 (ms)": f"{percentil(ms, 0.5):.0f} / {percentil(ms, 0.95):.0f}",
            "Tokens por pergunta (entrada / saída)": f"{ent:.0f} / {sai:.0f}",
            "Custo por pergunta no plano pago (US$)": f"{c:.6f}",
            "Custo por 1.000 perguntas (US$)": f"{1000 * c:.2f}",
        })
    for metrica in colunas[0]:
        tabela.append(f"| {metrica} | " + " | ".join(col[metrica] for col in colunas) + " |")
    linhas += tabela
    linhas += ["", "Latência = embedding + busca + chamada ao LLM, sem as esperas para respeitar o limite por minuto "
               "do plano grátis. Custo só do modelo de resposta (o juiz é custo da avaliação, não do uso).", "",
               "## Respostas marcadas pelo juiz (correta = nao, ou não fiel)", ""]
    for r in todos:
        if r["correta"] == "nao" or not r["fiel"]:
            extra = f" Sem suporte: {'; '.join(r['sem_suporte'])}." if r["sem_suporte"] else ""
            linhas.append(f"- k={r['k']} {r['id']} ({r['cobertura']}, correta={r['correta']}, fiel={r['fiel']}): "
                          f"{r['justificativa']}{extra}")
    (RAIZ / "resultados" / f"respostas{sufixo}.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    campos = ["k", "id", "tipo", "pergunta", "referencia", "resposta", "cobertura", "citados", "correta", "fiel",
              "sem_suporte", "justificativa", "citacao_correta", "recuperou_trecho", "ms_llm", "tokens_entrada",
              "tokens_saida"]
    with open(RAIZ / "resultados" / f"respostas{sufixo}.csv", "w", encoding="utf-8", newline="") as saida:
        escritor = csv.DictWriter(saida, fieldnames=campos, extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(todos)
    print(f"relatório: resultados/respostas{sufixo}.md")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--conjunto", choices=["avaliacao", "teste"], default="avaliacao")
    parser.add_argument("--limite", type=int)
    args = parser.parse_args()
    rodar(args.conjunto, args.k, args.limite)
    relatorio(args.conjunto)


if __name__ == "__main__":
    main()
