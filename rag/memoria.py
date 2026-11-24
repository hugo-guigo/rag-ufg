"""Memória das conversas no Postgres (decisão 6 de docs/specs/langgraph.md).

Na demo, a memória do processo (InMemorySaver) some quando o app vai a zero réplicas, depois de uns 5
minutos parado. Com o PostgresSaver, a conversa continua de onde parou mesmo em outra réplica.

- As tabelas são do próprio pacote (checkpoints, checkpoint_blobs, checkpoint_writes e
  checkpoint_migrations). Quem as cria é o admin, com preparar_memoria (scripts/preparar_memoria.py). O
  usuário app só recebe o que o checkpointer usa: ler, gravar e apagar checkpoints.
- O serializador é o mesmo de rag/agente_grafo.py, com a lista fechada de classes.
- Os checkpoints crescem a cada turno, por isso a API apaga, ao subir, as conversas paradas há mais de
  DIAS_DE_MEMORIA dias.
"""
from __future__ import annotations

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver

from rag.agente_grafo import SERIALIZADOR

DIAS_DE_MEMORIA = 7
TABELAS_DO_APP = ("checkpoints", "checkpoint_blobs", "checkpoint_writes")


def checkpointer_postgres(conexao) -> PostgresSaver:
    """conexao: uma Connection ou um ConnectionPool com autocommit (o pool da API já é assim).

    No Neon, a conexão passa pelo pooler, que não guarda comandos preparados: o pool da API já usa
    prepare_threshold=None. O from_conn_string do pacote liga os comandos preparados, por isso não é usado.
    """
    return PostgresSaver(conexao, serde=SERIALIZADOR)


def preparar_memoria(conexao_admin: psycopg.Connection) -> None:
    """Cria as tabelas (idempotente) e dá ao usuário app só o que o checkpointer usa. Rodar como admin."""
    PostgresSaver(conexao_admin).setup()  # CREATE INDEX CONCURRENTLY: a conexão precisa de autocommit
    conexao_admin.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {', '.join(TABELAS_DO_APP)} TO app")


def limpar_conversas_antigas(conexao, saver: PostgresSaver, dias: int = DIAS_DE_MEMORIA) -> int:
    """Apaga as conversas cujo último turno tem mais de `dias` dias. Devolve quantas apagou.

    O instante de cada checkpoint fica em checkpoint->>'ts'; uma conversa vale pelo mais recente.
    conexao: Connection ou ConnectionPool do mesmo banco do saver.
    """
    consulta = ("SELECT thread_id FROM checkpoints GROUP BY thread_id "
                "HAVING max((checkpoint->>'ts')::timestamptz) < now() - make_interval(days => %s)")
    if isinstance(conexao, psycopg.Connection):
        antigas = [linha[0] for linha in conexao.execute(consulta, (dias,))]
    else:
        with conexao.connection() as c:
            antigas = [linha[0] for linha in c.execute(consulta, (dias,))]
    for thread_id in antigas:
        saver.delete_thread(thread_id)
    return len(antigas)
