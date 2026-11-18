"""Monta o que a API usa a partir de variáveis de ambiente: pool do Postgres, embedder, Groq e agente.

Separado de app.py para os testes da API trocarem tudo isto por versões falsas.
"""
import os
from dataclasses import dataclass, field

from rag.agente import Agente, FontesPool
from rag.registro import Limites, Registro

MAX_ESPERA_GROQ = 8.0  # segundos somados de espera pelo limite por minuto antes de devolver 503


@dataclass
class Servicos:
    agente: object  # algo com perguntar(pergunta) -> RespostaAgente
    registro: object  # algo com contar, gravar e banco_ok, como rag.registro.Registro
    sal: str
    limites: Limites = field(default_factory=Limites)
    confiar_proxy: bool = False  # True atrás do proxy da nuvem, que informa o IP em X-Forwarded-For
    fechar: object = None


def _inteiro(nome: str, padrao: int) -> int:
    return int(os.environ.get(nome) or padrao)


def servicos_do_ambiente() -> Servicos:
    from pgvector.psycopg import register_vector
    from psycopg_pool import ConnectionPool

    from rag.embeddings import Embedder
    from rag.llm import ClienteGroq

    pool = ConnectionPool(
        os.environ["DATABASE_URL"], min_size=1, max_size=4, open=True,
        # prepare_threshold None: o pooler do Neon (PgBouncer em modo transação) não guarda comandos preparados
        kwargs={"autocommit": True, "prepare_threshold": None},
        configure=register_vector)
    embedder = Embedder("int8")
    embedder.pergunta("aquecimento")  # a primeira inferência do ONNX é mais lenta; paga no início
    agente = Agente(FontesPool(pool, embedder), ClienteGroq(max_espera=MAX_ESPERA_GROQ))
    limites = Limites(_inteiro("LIMITE_POR_MINUTO", 5), _inteiro("LIMITE_POR_DIA", 30),
                      _inteiro("LIMITE_TOTAL_POR_DIA", 50))
    return Servicos(agente, Registro(pool), os.environ["SAL_CLIENTE"], limites,
                    os.environ.get("CONFIAR_PROXY") == "1", pool.close)
