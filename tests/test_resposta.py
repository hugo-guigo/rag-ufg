from rag.busca import Resultado
from rag.resposta import formatar_trechos, rotulo, schema, validar_citacoes


def res(id_: str, artigo: int, contexto: str, p1: int = 25, p2: int = 25) -> Resultado:
    return Resultado(id_, "rgcg", f"Art. {artigo}. Texto.", contexto, (artigo,), p1, p2, 0.9)


A = res("rgcg-art082-p1", 82, "Seção I: Da Avaliação > Art. 82 (parte 1 de 2)")
B = res("rgcg-art087", 87, "Seção IV: Da Frequência > Art. 87", 27, 28)


def test_rotulo_usa_artigo_do_contexto_e_paginas():
    assert rotulo(A) == "RGCG, Art. 82 (parte 1 de 2), p. 25"
    assert rotulo(B) == "RGCG, Art. 87, p. 27-28"
    assert rotulo(res("x", 9, "")) == "RGCG, Art. 9, p. 25"


def test_trechos_rotulados_para_o_prompt():
    assert formatar_trechos([A, B]).startswith("T1 (RGCG, Art. 82 (parte 1 de 2), p. 25)\nArt. 82. Texto.\n\nT2 (")


def test_schema_so_aceita_rotulos_entregues():
    enum = schema(3)["properties"]["citacoes"]["items"]["enum"]
    assert enum == ["T1", "T2", "T3"]


def test_validar_citacoes_descarta_invalidas_e_repetidas():
    citados, invalidas = validar_citacoes(["T2", "T2", "T9", "75", "T1"], [A, B])
    assert citados == [B, A] and invalidas == 2
