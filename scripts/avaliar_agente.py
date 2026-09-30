"""Avalia o agente (etapa 5) nas 50 perguntas do conjunto de avaliação e compara com o RAG da etapa 4.

Uso: python scripts/avaliar_agente.py [--conjunto avaliacao|teste] [--limite N]
Gasta cota do Groq: ~2 a 6 mil tokens por pergunta no agente, mais ~1,5 mil no juiz.
Retoma de onde parou: cada pergunta fica em resultados/agente/<conjunto>.jsonl.
Relatório: resultados/agente[_teste].md e .csv

Ordem: calendário, mistas e sem resposta primeiro (o que a etapa 4 não cobria), regulamento por último.

Métricas determinísticas (sem juiz):
- ferramenta certa: regulamento -> buscar_regulamento; calendário -> consultar_calendario; misto -> as duas.
- trecho anotado entre os recuperados / citados (regulamento e mistas).
- eventos anotados entre os recuperados / citados (calendário e mistas), por evento.
Juiz (gpt-oss-120b): correta e fiel, como na etapa 4, com o prompt adaptado para citar eventos.
"""
import argparse
import csv
import json
import statistics
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from rag.agente import Agente, FontesBanco  # noqa: E402
from rag.banco import conectar  # noqa: E402
from rag.embeddings import Embedder  # noqa: E402
from rag.juiz import REFERENCIA_SEM_RESPOSTA_AGENTE, SISTEMA_AGENTE, julgar  # noqa: E402
from rag.llm import ClienteGroq, ErroLLM  # noqa: E402
from rag.metricas import contem_trecho, percentil, trechos_de  # noqa: E402

PASTA = RAIZ / "resultados" / "agente"
ORDEM = {"calendario": 0, "misto": 1, "sem_resposta": 2, "regulamento": 3}
HOJE = date(2026, 9, 29)  # fixo para a avaliação ser reproduzível
PRECO = {"openai/gpt-oss-20b": (0.075, 0.30)}  # US$ por milhão de tokens (entrada, saída), groq.com/pricing
TIPOS = ["regulamento", "calendario", "misto", "sem_resposta"]


def evento_bate(esperado: dict, e) -> bool:
    return (e.data_inicio.isoformat() == esperado["inicio"] and e.data_fim.isoformat() == esperado["fim"]
            and esperado["contem"] in e.descricao)


def rodar(conjunto: str, limite: int | None) -> None:
    perguntas = json.loads((RAIZ / "dados" / f"{conjunto}.json").read_text(encoding="utf-8"))
    perguntas.sort(key=lambda p: ORDEM[p["tipo"]])
    PASTA.mkdir(parents=True, exist_ok=True)
    arquivo = PASTA / f"{conjunto}.jsonl"
    feitos = {json.loads(linha)["id"] for linha in arquivo.open(encoding="utf-8")} if arquivo.exists() else set()
    pendentes = [p for p in perguntas if p["id"] not in feitos][:limite]
    print(f"{conjunto}: {len(feitos)} já feitas, {len(pendentes)} agora")
    if not pendentes:
        return
    embedder, cliente = Embedder("int8"), ClienteGroq()
    embedder.pergunta("aquecimento")
    agente = Agente(FontesBanco(conectar(), embedder), cliente, hoje=HOJE)
    for p in pendentes:
        quebradas, dobrados, consertadas = cliente.chamadas_quebradas, cliente.limites_dobrados, cliente.chamadas_consertadas
        try:
            r = agente.perguntar(p["pergunta"])
            referencia = p.get("resposta", REFERENCIA_SEM_RESPOSTA_AGENTE)
            j = julgar(cliente, p["pergunta"], referencia, r.resposta,
                       [(f"{rot} ({fonte})", texto) for rot, fonte, texto in r.citados], sistema=SISTEMA_AGENTE)
        except ErroLLM as erro:
            print(f"  {p['id']}: parei ({erro}). Rode de novo para continuar.")
            return
        trechos = trechos_de(p)
        recuperados = list(r.trechos.values())
        citados_t = [r.trechos[rot] for rot, _, _ in r.citados if rot in r.trechos]
        eventos = list(r.eventos.values())
        citados_e = [r.eventos[rot] for rot, _, _ in r.citados if rot in r.eventos]
        esperados = p.get("eventos", [])
        registro = {
            "id": p["id"], "tipo": p["tipo"], "pergunta": p["pergunta"], "referencia": referencia,
            "resposta": r.resposta, "cobertura": r.cobertura, "citados": [c[0] + " " + c[1] for c in r.citados],
            "passos": [{"ferramenta": x.ferramenta, "argumentos": x.argumentos, "resultados": len(x.resultados),
                        "erro": x.erro} for x in r.passos],
            "usou_regulamento": r.usou("buscar_regulamento"), "usou_calendario": r.usou("consultar_calendario"),
            "recuperou_trecho": any(contem_trecho(c.texto, t) for c in recuperados for t in trechos) if trechos else None,
            "citou_trecho": any(contem_trecho(c.texto, t) for c in citados_t for t in trechos) if trechos else None,
            "eventos_esperados": len(esperados),
            "eventos_recuperados": sum(any(evento_bate(x, e) for e in eventos) for x in esperados),
            "eventos_citados": sum(any(evento_bate(x, e) for e in citados_e) for x in esperados),
            "correta": j.conteudo["correta"], "fiel": j.conteudo["fiel"], "sem_suporte": j.conteudo["sem_suporte"],
            "justificativa": j.conteudo["justificativa"],
            "chamadas_llm": r.chamadas_llm, "forcou_resposta": r.forcou_resposta, "erros_ferramenta": r.erros_ferramenta,
            "citacoes_invalidas": r.citacoes_invalidas, "chamadas_quebradas": cliente.chamadas_quebradas - quebradas,
            "limites_dobrados": cliente.limites_dobrados - dobrados,
            "chamadas_consertadas": cliente.chamadas_consertadas - consertadas,
            "ms_llm": r.ms_llm, "ms_llm_total": r.ms_llm_total, "ms_ferramentas": r.ms_ferramentas,
            "tokens_entrada": r.tokens_entrada, "tokens_saida": r.tokens_saida, "modelo": r.modelo,
            "juiz_tokens_entrada": j.tokens_entrada, "juiz_tokens_saida": j.tokens_saida,
        }
        with arquivo.open("a", encoding="utf-8") as saida:
            saida.write(json.dumps(registro, ensure_ascii=False) + "\n")
        print(f"  {p['id']:4} {r.cobertura:8} correta={registro['correta']:7} fiel={registro['fiel']!s:5} "
              f"{r.chamadas_llm} chamadas, {r.tokens_entrada} tokens")


def pct(n: int, total: int) -> str:
    return f"{n}/{total} ({100 * n / total:.0f}%)" if total else "-"


def ferramenta_certa(r: dict) -> bool:
    return {"regulamento": r["usou_regulamento"], "calendario": r["usou_calendario"],
            "misto": r["usou_regulamento"] and r["usou_calendario"]}[r["tipo"]]


def relatorio(conjunto: str) -> None:
    arquivo = PASTA / f"{conjunto}.jsonl"
    if not arquivo.exists():
        return
    regs = [json.loads(linha) for linha in arquivo.open(encoding="utf-8")]
    por_tipo = {t: [r for r in regs if r["tipo"] == t] for t in TIPOS}
    linhas = [f"# Avaliação do agente (etapa 5), conjunto {conjunto}", "",
              "Gerado por scripts/avaliar_agente.py. Modelo do agente: openai/gpt-oss-20b, até 4 chamadas por pergunta. "
              "Juiz: openai/gpt-oss-120b. Ferramentas: buscar_regulamento (vetorial, artigo com seção, k=5) e "
              "consultar_calendario (híbrida com filtro de datas, até 8 eventos).", "",
              f"Perguntas avaliadas: {len(regs)} de 50.", "", "## Por tipo de pergunta", "",
              "| Métrica | Regulamento | Calendário | Mistas | Sem resposta |", "|---|---|---|---|---|"]

    def linha(nome, f):
        linhas.append(f"| {nome} | " + " | ".join(f(por_tipo[t], t) for t in TIPOS) + " |")

    linha("Perguntas", lambda rs, t: str(len(rs)))
    linha("Correta (juiz: sim)", lambda rs, t: pct(sum(r["correta"] == "sim" for r in rs), len(rs)))
    linha("Correta ou parcial", lambda rs, t: pct(sum(r["correta"] != "nao" for r in rs), len(rs)))
    linha("Fiel às fontes citadas (juiz)", lambda rs, t: pct(sum(r["fiel"] for r in rs if r["cobertura"] != "nenhuma"),
                                                             sum(r["cobertura"] != "nenhuma" for r in rs)))
    linha("Ferramenta certa", lambda rs, t: "-" if t == "sem_resposta" else pct(sum(ferramenta_certa(r) for r in rs), len(rs)))
    linha("Trecho anotado recuperado", lambda rs, t: pct(sum(bool(r["recuperou_trecho"]) for r in rs), len(rs))
          if t in ("regulamento", "misto") else "-")
    linha("Trecho anotado citado", lambda rs, t: pct(sum(bool(r["citou_trecho"]) for r in rs), len(rs))
          if t in ("regulamento", "misto") else "-")
    linha("Eventos anotados recuperados", lambda rs, t: pct(sum(r["eventos_recuperados"] for r in rs),
                                                             sum(r["eventos_esperados"] for r in rs))
          if t in ("calendario", "misto") else "-")
    linha("Eventos anotados citados", lambda rs, t: pct(sum(r["eventos_citados"] for r in rs),
                                                         sum(r["eventos_esperados"] for r in rs))
          if t in ("calendario", "misto") else "-")
    linha("\"Não sei\" (cobertura nenhuma)", lambda rs, t: pct(sum(r["cobertura"] == "nenhuma" for r in rs), len(rs)))
    linha("Chamadas ao LLM (média)", lambda rs, t: f"{statistics.mean(r['chamadas_llm'] for r in rs):.1f}" if rs else "-")

    ms = [r["ms_llm"] + r["ms_ferramentas"] for r in regs]
    ent = statistics.mean(r["tokens_entrada"] for r in regs)
    sai = statistics.mean(r["tokens_saida"] for r in regs)
    pe, ps = PRECO[regs[0]["modelo"]]
    custo = (ent * pe + sai * ps) / 1e6
    linhas += ["", "## Operação (todas as perguntas)", "", "| Métrica | Valor |", "|---|---|",
               f"| Respostas forçadas no último passo | {sum(r['forcou_resposta'] for r in regs)} |",
               f"| Erros de ferramenta devolvidos ao modelo | {sum(r['erros_ferramenta'] for r in regs)} |",
               f"| Citações inválidas descartadas | {sum(r['citacoes_invalidas'] for r in regs)} |",
               f"| Chamadas de ferramenta malformadas (repetidas) | {sum(r['chamadas_quebradas'] for r in regs)} |",
               f"| Chamadas com sufixo do Harmony no nome (consertadas) | {sum(r.get('chamadas_consertadas', 0) for r in regs)} |",
               f"| Latência p50 / p95 (ms) | {percentil(ms, 0.5):.0f} / {percentil(ms, 0.95):.0f} |",
               f"| Tokens por pergunta (entrada / saída) | {ent:.0f} / {sai:.0f} |",
               f"| Custo por 1.000 perguntas no plano pago (US$) | {1000 * custo:.2f} |",
               "", "Latência = chamadas ao LLM + ferramentas (embedding e SQL), sem as esperas do limite por minuto do "
               "plano grátis. Custo só do agente, sem o juiz."]

    etapa4 = PASTA.parent / "respostas" / f"{conjunto}_k5.jsonl"
    rag = {r["id"]: r for r in map(json.loads, etapa4.open(encoding="utf-8"))} if etapa4.exists() else {}
    pares = [(rag[r["id"]], r) for r in regs if r["id"] in rag]
    if pares:
        com = [(a, b) for a, b in pares if b["tipo"] == "regulamento"]
        sem = [(a, b) for a, b in pares if b["tipo"] == "sem_resposta"]
        ganhou = [b["id"] for a, b in com if a["correta"] != "sim" and b["correta"] == "sim"]
        perdeu = [b["id"] for a, b in com if a["correta"] == "sim" and b["correta"] != "sim"]
        linhas += ["", "## Agente vs RAG da etapa 4 (mesmas perguntas)", "",
                   "| Métrica | RAG etapa 4 (k=5) | Agente |", "|---|---|---|",
                   f"| Regulamento: correta (juiz: sim) | {pct(sum(a['correta'] == 'sim' for a, _ in com), len(com))} | "
                   f"{pct(sum(b['correta'] == 'sim' for _, b in com), len(com))} |",
                   f"| Regulamento: correta ou parcial | {pct(sum(a['correta'] != 'nao' for a, _ in com), len(com))} | "
                   f"{pct(sum(b['correta'] != 'nao' for _, b in com), len(com))} |",
                   f"| Regulamento: trecho anotado recuperado | {pct(sum(bool(a['recuperou_trecho']) for a, _ in com), len(com))} | "
                   f"{pct(sum(bool(b['recuperou_trecho']) for _, b in com), len(com))} |",
                   f"| Sem resposta: \"não sei\" | {pct(sum(a['cobertura'] == 'nenhuma' for a, _ in sem), len(sem))} | "
                   f"{pct(sum(b['cobertura'] == 'nenhuma' for _, b in sem), len(sem))} |",
                   f"| Tokens de entrada por pergunta | {statistics.mean(a['tokens_entrada'] for a, _ in pares):.0f} | "
                   f"{statistics.mean(b['tokens_entrada'] for _, b in pares):.0f} |",
                   "", f"No regulamento, o agente acertou e o RAG não: {', '.join(ganhou) or 'nenhuma'}. "
                   f"O RAG acertou e o agente não: {', '.join(perdeu) or 'nenhuma'}.",
                   "Calendário e mistas não entram na comparação: o RAG da etapa 4 só busca no regulamento."]

    linhas += ["", "## Respostas marcadas pelo juiz (correta = nao ou parcial, ou não fiel)", ""]
    for r in regs:
        if r["correta"] != "sim" or not r["fiel"]:
            extra = f" Sem suporte: {'; '.join(r['sem_suporte'])}." if r["sem_suporte"] else ""
            ferramentas = ", ".join(f"{x['ferramenta']}({json.dumps(x['argumentos'], ensure_ascii=False)})"
                                    for x in r["passos"] if x["ferramenta"] != "responder")
            linhas.append(f"- {r['id']} ({r['tipo']}, {r['cobertura']}, correta={r['correta']}, fiel={r['fiel']}): "
                          f"{r['justificativa']}{extra} Ferramentas: {ferramentas}.")
    sufixo = "_teste" if conjunto == "teste" else ""
    (RAIZ / "resultados" / f"agente{sufixo}.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    campos = ["id", "tipo", "pergunta", "referencia", "resposta", "cobertura", "citados", "correta", "fiel",
              "sem_suporte", "justificativa", "usou_regulamento", "usou_calendario", "recuperou_trecho", "citou_trecho",
              "eventos_esperados", "eventos_recuperados", "eventos_citados", "chamadas_llm", "erros_ferramenta",
              "ms_llm", "ms_ferramentas", "tokens_entrada", "tokens_saida"]
    with open(RAIZ / "resultados" / f"agente{sufixo}.csv", "w", encoding="utf-8", newline="") as saida:
        escritor = csv.DictWriter(saida, fieldnames=campos, extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(regs)
    print(f"relatório: resultados/agente{sufixo}.md")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--conjunto", choices=["avaliacao", "teste"], default="avaliacao")
    parser.add_argument("--limite", type=int)
    args = parser.parse_args()
    rodar(args.conjunto, args.limite)
    relatorio(args.conjunto)


if __name__ == "__main__":
    main()
