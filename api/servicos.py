"""Monta o que a API usa a partir de variáveis de ambiente: pool do Postgres, embedder, Groq e agente.

Separado de app.py para os testes da API trocarem tudo isto por versões falsas.
"""
import os
from dataclasses import dataclass, field

from rag.agente import Agente
from rag.busca import buscar, buscar_eventos
from rag.registro import Limites, Registro

MAX_ESPERA_GROQ = 8.0  # segundos somados de espera pelo limite por minuto antes de devolver 503


class FontesPool:
    """As ferramentas do agente com uma conexão do pool por consulta (a API atende em várias threads)."""

    def __init__(self, pool, embedder, k: int = 5, n_eventos: int = 8):
        self.pool, self.embedder, self.k, self.n_eventos = pool, embedder, k, n_eventos

    def buscar_regulamento(self, consulta):
        vetor = self.embedder.pergunta(consulta)
        with self.pool.connection() as conexao:
            return buscar(conexao, vetor, self.k, "artigo_secao", self.embedder.nome)

    def consultar_calendario(self, termo, inicio, fim):
        vetor = self.embedder.pergunta(termo) if termo.strip() else None
        with self.pool.connection() as conexao:
            return buscar_eventos(conexao, vetor, termo, inicio, fim, self.n_eventos)


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
