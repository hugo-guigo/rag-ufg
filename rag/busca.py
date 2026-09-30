"""Busca de trechos no Postgres: vetorial (pgvector), por palavra-chave (full-text) ou híbrida.

- vetor: `<=>` é a distância de cosseno do pgvector (1 - cosseno). Com vetores de norma 1, ordenar por
  ela é o mesmo que ordenar pelo produto escalar. A busca é exata: compara com todos os trechos.
- texto: full-text do Postgres com radicais do português ("trancar" e "trancamento" viram "tranc").
  A pergunta vira um OU entre os radicais dela, e ts_rank ordena pela frequência dos termos.
- hibrida: junta as duas listas por Reciprocal Rank Fusion (RRF): cada trecho soma 1/(60 + posição)
  em cada lista em que aparece. Não precisa calibrar as notas das duas buscas, que estão em escalas
  diferentes; só as posições importam. O 60 é a constante do artigo original do RRF (Cormack et al., 2009).

A similaridade devolvida é sempre o cosseno com a pergunta, qualquer que seja o modo, para o limiar de
"não sei" usar a mesma escala.

Calendário (buscar_eventos): mesma fusão RRF, entre o vetor da descrição do evento e o full-text, com
filtro opcional de datas. No full-text do calendário cada radical vira prefixo ('tranc':*), porque o
radicalizador do português separa "trancar" (tranc) de "trancamento" (trancament). Medido nas 10
perguntas de calendário e mistas: com a pergunta inteira como consulta e sem datas, texto com E achou
2 de 15 eventos, texto com OU por prefixo 8, vetor 7 e a fusão 9; com termo curto e intervalo de
datas, a fusão achou os 15.
"""
from dataclasses import dataclass
from datetime import date

import numpy as np
import psycopg

MODOS = ("vetor", "texto", "hibrida")
CANDIDATOS = 20  # quantos trechos cada busca entrega para a fusão
RRF_K = 60

COLUNAS = "t.id, t.documento, t.texto, t.contexto, t.artigos, t.pagina_inicio, t.pagina_fim, " \
          "1 - (t.embedding <=> %(v)s) AS similaridade"

CONSULTA_TEXTO = """
    q AS (SELECT to_tsquery('portuguese', coalesce(string_agg(quote_literal(lexeme), ' | '), '')) AS q
          FROM unnest(to_tsvector('portuguese', %(p)s))),
    txt AS (SELECT t.id, row_number() OVER (ORDER BY ts_rank(t.tsv, q.q, 1) DESC, t.id) AS pos
            FROM trechos t, q
            WHERE t.estrategia = %(e)s AND t.modelo = %(m)s AND t.tsv @@ q.q
            ORDER BY pos LIMIT %(n)s)
"""

SQL = {
    "vetor": f"""
        SELECT {COLUNAS} FROM trechos t
        WHERE t.estrategia = %(e)s AND t.modelo = %(m)s
        ORDER BY t.embedding <=> %(v)s LIMIT %(k)s""",
    "texto": f"""
        WITH {CONSULTA_TEXTO}
        SELECT {COLUNAS} FROM txt JOIN trechos t ON t.id = txt.id AND t.estrategia = %(e)s AND t.modelo = %(m)s
        ORDER BY txt.pos LIMIT %(k)s""",
    "hibrida": f"""
        WITH vet AS (SELECT t.id, row_number() OVER (ORDER BY t.embedding <=> %(v)s) AS pos
                     FROM trechos t WHERE t.estrategia = %(e)s AND t.modelo = %(m)s
                     ORDER BY t.embedding <=> %(v)s LIMIT %(n)s),
        {CONSULTA_TEXTO},
        fusao AS (SELECT id, sum(1.0 / (%(c)s + pos)) AS rrf
                  FROM (SELECT id, pos FROM vet UNION ALL SELECT id, pos FROM txt) u GROUP BY id)
        SELECT {COLUNAS} FROM fusao f JOIN trechos t ON t.id = f.id AND t.estrategia = %(e)s AND t.modelo = %(m)s
        ORDER BY f.rrf DESC, t.id LIMIT %(k)s""",
}


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


def buscar(conexao: psycopg.Connection, vetor: np.ndarray, k: int = 5, estrategia: str = "artigo_secao",
           modelo: str = "multilingual-e5-small-int8", modo: str = "vetor", pergunta: str = "") -> list[Resultado]:
    if modo not in MODOS:
        raise ValueError(f"modo deve ser um de {MODOS}")
    parametros = {"v": vetor, "e": estrategia, "m": modelo, "k": k, "p": pergunta, "n": CANDIDATOS, "c": RRF_K}
    linhas = conexao.execute(SQL[modo], parametros).fetchall()
    return [Resultado(r[0], r[1], r[2], r[3], tuple(r[4]), r[5], r[6], float(r[7])) for r in linhas]


SQL_EVENTOS = """
    WITH filtrados AS (
        SELECT * FROM eventos_calendario
        WHERE embedding IS NOT NULL
          AND (%(ini)s::date IS NULL OR data_fim >= %(ini)s::date)
          AND (%(fim)s::date IS NULL OR data_inicio <= %(fim)s::date)),
    vet AS (SELECT id, row_number() OVER (ORDER BY embedding <=> %(v)s, id) AS pos FROM filtrados),
    q AS (SELECT to_tsquery('portuguese', coalesce(string_agg(quote_literal(lexeme) || ':*', ' | '), ''))
                 AS q FROM unnest(to_tsvector('portuguese', unaccent(%(t)s)))),
    txt AS (SELECT f.id, row_number() OVER (
                ORDER BY ts_rank(to_tsvector('portuguese', unaccent(f.descricao)), q.q, 1) DESC, f.id) AS pos
            FROM filtrados f, q WHERE to_tsvector('portuguese', unaccent(f.descricao)) @@ q.q),
    fusao AS (SELECT id, sum(1.0 / (%(c)s + pos)) AS rrf
              FROM (SELECT id, pos FROM vet UNION ALL SELECT id, pos FROM txt) u GROUP BY id)
    SELECT e.id, e.data_inicio, e.data_fim, e.descricao, e.pagina FROM fusao f JOIN eventos_calendario e USING (id)
    ORDER BY f.rrf DESC, e.id LIMIT %(n)s"""

SQL_EVENTOS_SO_DATAS = """
    SELECT id, data_inicio, data_fim, descricao, pagina FROM eventos_calendario
    WHERE data_fim >= %(ini)s::date AND data_inicio <= %(fim)s::date
    ORDER BY data_inicio, id LIMIT %(n)s"""


@dataclass(frozen=True)
class Evento:
    id: int
    data_inicio: date
    data_fim: date
    descricao: str
    pagina: int


def buscar_eventos(conexao: psycopg.Connection, vetor: np.ndarray | None, termo: str = "",
                   inicio: date | None = None, fim: date | None = None, n: int = 8) -> list[Evento]:
    """Eventos mais relevantes para o termo dentro do intervalo, em ordem de data.

    Sem termo, devolve os primeiros eventos do intervalo (ex.: "o que acontece em novembro?").
    """
    if not termo.strip():
        if not (inicio and fim):
            raise ValueError("informe um termo ou um intervalo de datas completo")
        linhas = conexao.execute(SQL_EVENTOS_SO_DATAS, {"ini": inicio, "fim": fim, "n": n}).fetchall()
    else:
        linhas = conexao.execute(SQL_EVENTOS, {"v": vetor, "t": termo, "ini": inicio, "fim": fim, "n": n,
                                               "c": RRF_K}).fetchall()
    eventos = [Evento(*linha) for linha in linhas]
    return sorted(eventos, key=lambda e: (e.data_inicio, e.id))
