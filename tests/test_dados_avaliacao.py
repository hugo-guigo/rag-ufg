"""Confere as anotações dos conjuntos contra os documentos, para um erro de digitação na anotação não
virar um "erro do modelo" na tabela de resultados.

avaliacao.json: 50 perguntas escritas com auxílio de IA e revisadas pelo Hugo; usadas para escolher a configuração.
teste.json: 10 perguntas escritas pelo Hugo sem ver as outras; rodadas uma vez, no fim.
"""
import json
from datetime import date
from pathlib import Path

import pytest

from rag.calendario import ler_csv
from rag.extrair import ler_linhas
from rag.fontes import carregar_fontes
from rag.metricas import contem_trecho, trechos_de
from rag.regulamento import paragrafos_rgcg

RAIZ = Path(__file__).resolve().parent.parent
CONJUNTOS = {nome: json.loads((RAIZ / "dados" / f"{nome}.json").read_text(encoding="utf-8"))
             for nome in ("avaliacao", "teste")}
TIPOS = {"regulamento", "calendario", "misto", "sem_resposta"}
RGCG = next(f for f in carregar_fontes() if f.id == "rgcg")


@pytest.mark.parametrize("nome", CONJUNTOS)
def test_ids_unicos_tipos_validos(nome):
    perguntas = CONJUNTOS[nome]
    assert len({p["id"] for p in perguntas}) == len(perguntas)
    assert {p["tipo"] for p in perguntas} <= TIPOS
    for p in perguntas:
        if p["tipo"] == "sem_resposta":
            assert "artigos" not in p and "eventos" not in p
        else:
            assert p["resposta"]


def test_tamanhos_e_conjuntos_separados():
    assert len(CONJUNTOS["avaliacao"]) == 50 and len(CONJUNTOS["teste"]) == 10
    assert {p["tipo"] for p in CONJUNTOS["avaliacao"]} == TIPOS
    ids = [p["id"] for c in CONJUNTOS.values() for p in c]
    assert len(set(ids)) == len(ids)


@pytest.mark.parametrize("nome", CONJUNTOS)
def test_eventos_anotados_existem_no_calendario(nome):
    eventos = ler_csv(RAIZ / "dados" / "calendario_2026.csv")
    for p in CONJUNTOS[nome]:
        for esperado in p.get("eventos", []):
            inicio, fim = date.fromisoformat(esperado["inicio"]), date.fromisoformat(esperado["fim"])
            assert any(e.data_inicio == inicio and e.data_fim == fim and esperado["contem"] in e.descricao
                       for e in eventos), (p["id"], esperado)


@pytest.mark.skipif(not RGCG.caminho.exists(), reason="rode python -m rag.fontes antes")
@pytest.mark.parametrize("nome", CONJUNTOS)
def test_cada_trecho_anotado_esta_num_dos_artigos_anotados(nome):
    por_artigo: dict[int, str] = {}
    for par in paragrafos_rgcg(ler_linhas(RGCG.caminho)):
        por_artigo[par.artigo] = por_artigo.get(par.artigo, "") + "\n" + par.texto
    for p in CONJUNTOS[nome]:
        for trecho in trechos_de(p):
            assert any(contem_trecho(por_artigo[a], trecho) for a in p["artigos"]), (p["id"], trecho)
