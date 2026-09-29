"""Busca por similaridade no pgvector.

`<=>` é a distância de cosseno do pgvector (1 - cosseno). Como os vetores têm norma 1, ordenar por ela
é o mesmo que ordenar pelo produto escalar. A busca é exata: compara a pergunta com todos os trechos
da estratégia pedida.
"""
from dataclasses import dataclass

import numpy as np
import psycopg


@dataclass(frozen=True)
class Resultado:
    id: str
    documento: str
    texto: str
    contexto: str
    artigos: tuple[int, ...]
    pagina_inicio: int
    pagina_fim: int
    similaridade: float


def buscar(conexao: psycopg.Connection, vetor: np.ndarray, k: int = 5,
           estrategia: str = "artigo", modelo: str = "multilingual-e5-small-int8") -> list[Resultado]:
    linhas = conexao.execute(
        """
        SELECT id, documento, texto, contexto, artigos, pagina_inicio, pagina_fim,
               1 - (embedding <=> %(v)s) AS similaridade
        FROM trechos
        WHERE estrategia = %(e)s AND modelo = %(m)s
        ORDER BY embedding <=> %(v)s
        LIMIT %(k)s
        """,
        {"v": vetor, "e": estrategia, "m": modelo, "k": k},
    ).fetchall()
    return [Resultado(r[0], r[1], r[2], r[3], tuple(r[4]), r[5], r[6], float(r[7])) for r in linhas]
