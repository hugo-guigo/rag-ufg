"""Memória das conversas no Postgres de verdade, com o usuário app, como na API.

Rodar: RODAR_INTEGRACAO=1 pytest -m integracao (precisa do docker compose, de scripts/preparar_banco.py e de
scripts/preparar_memoria.py). O LLM é o falso de tests/test_agente.py: não gasta cota.
"""
import os
import uuid
from datetime import date

import pytest

from tests.test_agente import FontesFalsas, LLMRoteirizado, chamada, responder

pytestmark = [
    pytest.mark.integracao,
    pytest.mark.skipif(os.environ.get("RODAR_INTEGRACAO") != "1", reason="defina RODAR_INTEGRACAO=1"),
]

HOJE = date(2026, 9, 29)


@pytest.fixture
def bancos():
    from dotenv import load_dotenv
    from psycopg_pool import ConnectionPool

    from rag.banco import conectar

    load_dotenv()
    admin = conectar(admin=True)
    # Igual ao pool da API (api/servicos.py): autocommit e sem comandos preparados.
    pool = ConnectionPool(os.environ["DATABASE_URL"], min_size=1, max_size=2, open=True,
                          kwargs={"autocommit": True, "prepare_threshold": None})
    threads: list[str] = []
    yield admin, pool, threads
    for thread_id in threads:
        for tabela in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
            admin.execute(f"DELETE FROM {tabela} WHERE thread_id = %s", (thread_id,))
    pool.close()
    admin.close()


def agente(pool, rodadas):
    from rag.agente_grafo import AgenteGrafo
    from rag.memoria import checkpointer_postgres

    llm = LLMRoteirizado(rodadas)
    return AgenteGrafo(FontesFalsas(), llm, hoje=HOJE, checkpointer=checkpointer_postgres(pool)), llm


def test_conversa_continua_depois_de_reiniciar_o_app(bancos):
    _, pool, threads = bancos
    thread_id = f"teste-{uuid.uuid4()}"
    threads.append(thread_id)

    primeiro, _ = agente(pool, [[chamada("buscar_regulamento", {"consulta": "trancar"}, 1)],
                                [responder(resposta="Até 4 semestres (Art. 73).", citacoes=["T1"])]])
    primeiro.perguntar("Quantas vezes posso trancar o curso?", thread_id=thread_id)

    # Outro processo (outra réplica, ou o app depois de ir a zero): só o banco liga os dois turnos.
    segundo, llm = agente(pool, [[responder(resposta="Não, salvo exceções (Art. 75).")]])
    r = segundo.perguntar("Posso logo no primeiro semestre?", thread_id=thread_id)

    mensagens = llm.pedidos[0]["mensagens"]
    assert [m["role"] for m in mensagens] == ["system", "user", "assistant", "user"]
    assert mensagens[2]["content"] == "Até 4 semestres (Art. 73)."
    assert not any(m["role"] == "tool" for m in mensagens)  # as saídas das ferramentas não voltam
    assert r.chamadas_llm == 1 and r.resposta == "Não, salvo exceções (Art. 75)."


def test_limpeza_apaga_so_as_conversas_paradas_ha_mais_de_7_dias(bancos):
    from rag.memoria import checkpointer_postgres, limpar_conversas_antigas

    admin, pool, threads = bancos
    antiga, recente = f"teste-antiga-{uuid.uuid4()}", f"teste-recente-{uuid.uuid4()}"
    threads += [antiga, recente]
    for thread_id in (antiga, recente):
        a, _ = agente(pool, [[responder(resposta="ok")]])
        a.perguntar("Quando começa 2026/2?", thread_id=thread_id)
    # Envelhece a conversa "antiga" (só o admin altera; o app não precisa de UPDATE em ts).
    admin.execute("UPDATE checkpoints SET checkpoint = jsonb_set(checkpoint, '{ts}', "
                  "to_jsonb((now() - interval '8 days')::text)) WHERE thread_id = %s", (antiga,))

    apagadas = limpar_conversas_antigas(pool, checkpointer_postgres(pool))  # como a API: usuário app

    restantes = {linha[0] for linha in admin.execute(
        "SELECT DISTINCT thread_id FROM checkpoints WHERE thread_id = ANY(%s)", ([antiga, recente],))}
    assert restantes == {recente} and apagadas >= 1


def test_app_nao_cria_tabelas_nem_mexe_no_resto(bancos):
    import psycopg

    _, pool, _ = bancos
    with pool.connection() as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("CREATE TABLE intrusa (x int)")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("DELETE FROM checkpoint_migrations")
