"""Confere as anotações do conjunto de avaliação contra os documentos, para um erro de digitação
na anotação não virar um "erro do modelo" na tabela de resultados."""
import json
from datetime import date
from pathlib import Path

import pytest

from rag.calendario import ler_csv
from rag.extrair import ler_linhas
from rag.fontes import carregar_fontes
from rag.metricas import contem_trecho
from rag.regulamento import paragrafos_rgcg

RAIZ = Path(__file__).resolve().parent.parent
PERGUNTAS = json.loads((RAIZ / "dados" / "avaliacao.json").read_text(encoding="utf-8"))
RGCG = next(f for f in carregar_fontes() if f.id == "rgcg")


def test_ids_unicos_tipos_validos_e_tamanho():
    assert len({p["id"] for p in PERGUNTAS}) == len(PERGUNTAS)
    assert {p["tipo"] for p in PERGUNTAS} == {"regulamento", "calendario", "misto", "sem_resposta"}
    assert 30 <= len(PERGUNTAS) <= 50
    for p in PERGUNTAS:
        if p["tipo"] == "sem_resposta":
            assert "artigos" not in p and "eventos" not in p
        else:
            assert p["resposta"]


def test_eventos_anotados_existem_no_calendario():
    eventos = ler_csv(RAIZ / "dados" / "calendario_2026.csv")
    for p in PERGUNTAS:
        for esperado in p.get("eventos", []):
            inicio, fim = date.fromisoformat(esperado["inicio"]), date.fromisoformat(esperado["fim"])
            assert any(e.data_inicio == inicio and e.data_fim == fim and esperado["contem"] in e.descricao
                       for e in eventos), (p["id"], esperado)


@pytest.mark.skipif(not RGCG.caminho.exists(), reason="rode python -m rag.fontes antes")
def test_trecho_anotado_esta_num_dos_artigos_anotados():
    por_artigo: dict[int, str] = {}
    for par in paragrafos_rgcg(ler_linhas(RGCG.caminho)):
        por_artigo[par.artigo] = por_artigo.get(par.artigo, "") + "\n" + par.texto
    for p in PERGUNTAS:
        if "trecho" in p:
            assert any(contem_trecho(por_artigo[a], p["trecho"]) for a in p["artigos"]), p["id"]
