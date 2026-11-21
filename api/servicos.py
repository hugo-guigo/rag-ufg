"""Monta o que a API usa a partir de variáveis de ambiente: pool do Postgres, embedder, Groq e agente.

Separado de app.py para os testes da API trocarem tudo isto por versões falsas.
"""
import os
from dataclasses import dataclass, field

from rag.agente import Agente, FontesPool
from rag.registro import Limites, Registro

MAX_ESPERA_GROQ = 8.0  # segundos somados de espera pelo limite por minuto antes de devolver 503
MOTORES = ("manual", "langgraph")


@dataclass
class Servicos:
    agente: object  # algo com perguntar(pergunta) -> RespostaAgente; com conversa=True, aceita thread_id
    registro: object  # algo com contar, gravar e banco_ok, como rag.registro.Registro
    sal: str
    limites: Limites = field(default_factory=Limites)
    confiar_proxy: bool = False  # True atrás do proxy da nuvem, que informa o IP em X-Forwarded-For
    fechar: object = None
    acervo: object = None  # o que as ferramentas MCP consultam (mcp_ufg.ferramentas.AcervoPool)
    registro_mcp: object = None  # tokens, limite e rastreio do MCP (mcp_ufg.http.RegistroMCP)


def _inteiro(nome: str, padrao: int) -> int:
    return int(os.environ.get(nome) or padrao)


def criar_agente(motor: str, fontes, cliente):
    """AGENTE_MOTOR=manual (padrão) ou langgraph. Só o langgraph aceita conversa (thread_id).

    Até o bloco 4 a memória das conversas fica no processo: some quando o app vai a zero réplicas.
    """
    if motor == "manual":
        return Agente(fontes, cliente)
    if motor == "langgraph":
        from rag.agente_grafo import AgenteGrafo, checkpointer_em_memoria

        return AgenteGrafo(fontes, cliente, checkpointer=checkpointer_em_memoria())
    raise ValueError(f"AGENTE_MOTOR inválido: {motor!r} (use um de {MOTORES})")


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
    fontes = FontesPool(pool, embedder)
    agente = criar_agente(os.environ.get("AGENTE_MOTOR") or "manual", fontes, ClienteGroq(max_espera=MAX_ESPERA_GROQ))
    limites = Limites(_inteiro("LIMITE_POR_MINUTO", 5), _inteiro("LIMITE_POR_DIA", 30),
                      _inteiro("LIMITE_TOTAL_POR_DIA", 50))
    from mcp_ufg.ferramentas import AcervoPool
    from mcp_ufg.http import RegistroMCP

    return Servicos(agente, Registro(pool), os.environ["SAL_CLIENTE"], limites,
                    os.environ.get("CONFIAR_PROXY") == "1", pool.close, AcervoPool(fontes, pool), RegistroMCP(pool))
