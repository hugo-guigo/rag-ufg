import pytest

from rag.regulamento import Paragrafo
from rag.trechos import empacotar, por_artigo, por_janela


def p(texto: str, artigo: int, pagina: int = 1) -> Paragrafo:
    return Paragrafo(texto, pagina, artigo, "Título I: X")


def test_artigo_curto_vira_um_trecho_com_contexto():
    ts = por_artigo([p("Art. 1º Curto.", 1), p("§ 1º Também curto.", 1), p("Art. 2º Outro.", 2)])
    assert [t.id for t in ts] == ["rgcg-art001", "rgcg-art002"]
    assert ts[0].texto == "Art. 1º Curto.\n§ 1º Também curto."
    assert ts[0].texto_para_embedding() == "Título I: X > Art. 1\nArt. 1º Curto.\n§ 1º Também curto."


def test_artigo_longo_divide_entre_paragrafos_e_numera_as_partes():
    grande = [p("Art. 9º " + "a" * 700, 9, 4), p("§ 1º " + "b" * 700, 9, 4), p("§ 2º " + "c" * 700, 9, 5)]
    ts = por_artigo(grande, max_chars=1500)
    assert [t.id for t in ts] == ["rgcg-art009-p1", "rgcg-art009-p2"]
    assert all(len(t.texto) <= 1500 for t in ts)
    assert ts[1].contexto.endswith("Art. 9 (parte 2 de 2)")
    assert (ts[1].pagina_inicio, ts[1].pagina_fim) == (5, 5)


def test_paragrafo_maior_que_o_limite_fica_sozinho():
    partes = empacotar([p("x" * 2000, 1), p("y", 1)], max_chars=1500)
    assert [len(parte) for parte in partes] == [1, 1]


def test_janela_cobre_todo_o_texto_com_sobreposicao():
    ps = [p(f"Art. {i}º " + " ".join(["palavra"] * 60), i, pagina=i) for i in range(1, 6)]
    ts = por_janela(ps, tamanho=300, sobreposicao=60)
    completo = "\n".join(x.texto for x in ps)
    assert all(len(t.texto) <= 300 for t in ts)
    assert ts[0].texto.startswith("Art. 1º") and completo.endswith(ts[-1].texto)
    for anterior, seguinte in zip(ts, ts[1:]):
        # o começo de cada janela repete o fim da anterior
        assert seguinte.texto.split()[0] in anterior.texto.split()[-15:]
    assert ts[0].artigos[0] == 1 and ts[-1].artigos[-1] == 5
    assert ts[-1].pagina_fim == 5


def test_janela_rejeita_sobreposicao_grande():
    with pytest.raises(ValueError):
        por_janela([p("Art. 1º x", 1)], tamanho=100, sobreposicao=60)
