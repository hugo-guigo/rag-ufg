import pytest

from rag.metricas import contem_trecho, melhor_limiar, mrr, percentil, posicao_do_acerto, recall_em_k


def test_contem_trecho_ignora_quebras_de_linha():
    assert contem_trecho("Art. 72.\n§ 2º Não será\ncomputado", "Não será computado")
    assert not contem_trecho("Art. 72.", "Art. 73")


def test_posicao_do_acerto():
    assert posicao_do_acerto([1, 5, 7], lambda x: x > 4) == 2
    assert posicao_do_acerto([1, 2], lambda x: x > 4) is None


def test_recall_e_mrr():
    posicoes = [1, 3, None, 2]
    assert recall_em_k(posicoes, 1) == 0.25
    assert recall_em_k(posicoes, 3) == 0.75
    assert mrr(posicoes, 3) == pytest.approx((1 + 1 / 3 + 0 + 1 / 2) / 4)
    assert mrr(posicoes, 1) == 0.25


def test_percentil_igual_ao_percentile_cont():
    assert percentil([4, 1, 3, 2], 0.5) == pytest.approx(2.5)
    assert percentil([1, 2, 3, 4], 0.95) == pytest.approx(3.85)
    assert percentil([], 0.5) is None


def test_melhor_limiar():
    limiar, acuracia = melhor_limiar([0.9, 0.85, 0.8], [0.7, 0.82])
    assert (limiar, acuracia) == (0.8, 0.8)  # erra só o 0.82 sem resposta; no empate fica o menor limiar
    assert melhor_limiar([0.9], [0.5]) == (0.9, 1.0)
