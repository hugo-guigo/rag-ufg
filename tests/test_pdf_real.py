"""Confere o parser no PDF de verdade. Pula se o PDF não foi baixado (python -m rag.fontes)."""
import pytest

from rag.extrair import ler_linhas
from rag.fontes import carregar_fontes
from rag.regulamento import paragrafos_rgcg
from rag.trechos import por_artigo, por_janela

RGCG = next(f for f in carregar_fontes() if f.id == "rgcg")
pytestmark = pytest.mark.skipif(not RGCG.caminho.exists(), reason="rode python -m rag.fontes antes")


@pytest.fixture(scope="module")
def paragrafos():
    return paragrafos_rgcg(ler_linhas(RGCG.caminho))


def test_rgcg_tem_os_132_artigos_em_ordem(paragrafos):
    vistos = []
    for p in paragrafos:
        if not vistos or vistos[-1] != p.artigo:
            vistos.append(p.artigo)
    assert vistos == list(range(1, 133))


def test_rgcg_por_artigo_respeita_limite_e_ids_unicos(paragrafos):
    ts = por_artigo(paragrafos)
    assert len({t.id for t in ts}) == len(ts)
    assert all(len(t.texto) <= 1500 for t in ts)
    assert all(2 <= t.pagina_inicio <= t.pagina_fim <= 40 for t in ts)


def test_rgcg_janela_cobre_todos_os_artigos(paragrafos):
    ts = por_janela(paragrafos)
    assert sorted({a for t in ts for a in t.artigos}) == list(range(1, 133))
