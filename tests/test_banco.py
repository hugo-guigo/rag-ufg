"""Testes no Postgres de verdade. Precisam do docker compose rodando e do scripts/ingerir.py já executado.

Rodar: RODAR_INTEGRACAO=1 pytest -m integracao   (PowerShell: $env:RODAR_INTEGRACAO=1; pytest -m integracao)
"""
import os

import numpy as np
import psycopg
import pytest

from rag.busca import buscar
from rag.embeddings import DIMENSAO

pytestmark = [
    pytest.mark.integracao,
    pytest.mark.skipif(os.environ.get("RODAR_INTEGRACAO") != "1", reason="defina RODAR_INTEGRACAO=1"),
]


def unitario(*coordenadas: float) -> np.ndarray:
    v = np.zeros(DIMENSAO, dtype=np.float32)
    v[: len(coordenadas)] = coordenadas
    return v / np.linalg.norm(v)


def test_busca_ordena_por_cosseno_e_filtra_estrategia_e_modelo():
    from rag.banco import conectar

    conexao = conectar(admin=True)
    with conexao.transaction(force_rollback=True):  # nada do teste fica no banco
        linhas = [("t-perto", "teste", unitario(1, 0.1)), ("t-longe", "teste", unitario(0, 1)),
                  ("t-meio", "teste", unitario(1, 1)), ("t-outra", "outra", unitario(1, 0))]
        for id_, estrategia, v in linhas:
            conexao.execute(
                """INSERT INTO trechos (id, estrategia, modelo, documento, texto, artigos,
                   pagina_inicio, pagina_fim, embedding) VALUES (%s, %s, 'modelo-teste', 'rgcg', 'x', '{1}', 1, 1, %s)""",
                (id_, estrategia, v))
        resultados = buscar(conexao, unitario(1, 0), k=3, estrategia="teste", modelo="modelo-teste")
    assert [r.id for r in resultados] == ["t-perto", "t-meio", "t-longe"]
    assert resultados[0].similaridade == pytest.approx(1 / np.sqrt(1.01), abs=1e-4)
    assert resultados[2].similaridade == pytest.approx(0.0, abs=1e-4)


def test_busca_por_texto_usa_radicais_e_hibrida_junta_as_duas():
    from rag.banco import conectar

    conexao = conectar()
    zero = unitario(1)  # o vetor não importa para o modo texto
    # "ouvintes" e "ouvinte" têm o mesmo radical; só o Art. 38 fala disso
    texto = buscar(conexao, zero, k=3, modo="texto", pergunta="alunos ouvintes")
    assert texto[0].artigos == (38,)
    assert buscar(conexao, zero, k=3, modo="texto", pergunta="de a o") == []  # só palavras vazias
    hibrida = buscar(conexao, zero, k=5, modo="hibrida", pergunta="alunos ouvintes")
    assert len(hibrida) == 5 and any(r.artigos == (38,) for r in hibrida)
    with pytest.raises(ValueError):
        buscar(conexao, zero, modo="bm25")


def test_usuario_app_so_le():
    from rag.banco import conectar

    conexao = conectar()
    assert conexao.execute("SELECT count(*) FROM trechos").fetchone()[0] > 0
    assert conexao.execute("SELECT count(*) FROM eventos_calendario").fetchone()[0] > 0
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conexao.execute("DELETE FROM trechos")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conexao.execute("INSERT INTO documentos VALUES ('x', 'x', 'x', repeat('0', 64))")
