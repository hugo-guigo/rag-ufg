"""MCP no Postgres de verdade: tokens, revogação, rastreio gravado, limite e as ferramentas no banco ingerido.

Rodar: RODAR_INTEGRACAO=1 pytest -m integracao (precisa do docker compose, da ingestão e de
scripts/preparar_banco.py depois desta etapa). O admin cria e revoga, e o usuário app confere, como na API.
"""
import os
import uuid

import pytest

pytestmark = [
    pytest.mark.integracao,
    pytest.mark.skipif(os.environ.get("RODAR_INTEGRACAO") != "1", reason="defina RODAR_INTEGRACAO=1"),
]


@pytest.fixture
def bancos():
    from dotenv import load_dotenv
    from pgvector.psycopg import register_vector
    from psycopg_pool import ConnectionPool

    from rag.banco import conectar

    load_dotenv()
    admin = conectar(admin=True)
    pool = ConnectionPool(os.environ["DATABASE_URL"], min_size=1, max_size=2, open=True,
                          kwargs={"autocommit": True}, configure=register_vector)
    criados: list[str] = []
    yield admin, pool, criados
    for cliente in criados:  # o app não apaga nada; a limpeza é do admin
        admin.execute("DELETE FROM chamadas_mcp WHERE cliente = %s", (cliente,))
        admin.execute("DELETE FROM clientes_mcp WHERE id = %s", (cliente,))
    pool.close()
    admin.close()


def test_token_criado_vale_so_como_hash_e_deixa_de_valer_quando_revogado(bancos):
    from mcp_ufg.http import RegistroMCP, criar_cliente, hash_token, revogar_cliente

    admin, pool, criados = bancos
    cliente = f"teste-{uuid.uuid4().hex[:8]}"
    criados.append(cliente)
    token = criar_cliente(admin, cliente)
    assert token.startswith("ufgmcp_") and len(token) > 40
    guardado = admin.execute("SELECT token_sha256 FROM clientes_mcp WHERE id = %s", (cliente,)).fetchone()[0]
    assert guardado == hash_token(token) and token not in guardado

    registro = RegistroMCP(pool)
    assert registro.cliente_do_token(token) == cliente
    assert registro.cliente_do_token(token + "x") is None
    assert revogar_cliente(admin, cliente) is True
    assert registro.cliente_do_token(token) is None
    assert revogar_cliente(admin, cliente) is False  # já revogado


def test_rastreio_gravado_conta_para_o_limite(bancos):
    from mcp_ufg.http import RegistroMCP, criar_cliente
    from rag.registro import Limites

    admin, pool, criados = bancos
    cliente = f"teste-{uuid.uuid4().hex[:8]}"
    criados.append(cliente)
    criar_cliente(admin, cliente)
    registro = RegistroMCP(pool)
    for i in range(3):
        registro.gravar({"rastreio": f"r{i}", "requisicao": str(i), "cliente": cliente, "ferramenta": "buscar_regulamento",
                         "argumentos": {"pergunta_chars": 10, "k": 5}, "ok": True, "erro": None, "ms": 12.6, "bytes": 900})
    contagem = registro.contar(cliente)
    assert (contagem.no_minuto, contagem.no_dia) == (3, 3)
    assert contagem.bloqueio(Limites(por_minuto=3, por_dia=100, total_por_dia=10_000))[1] == 60
    linha = admin.execute("SELECT argumentos, ms FROM chamadas_mcp WHERE cliente = %s AND rastreio = 'r0'",
                          (cliente,)).fetchone()
    assert linha == ({"pergunta_chars": 10, "k": 5}, 13)


def test_ferramentas_no_banco_ingerido_devolvem_o_mesmo_que_a_busca_direta(bancos):
    from mcp_ufg import ferramentas
    from mcp_ufg.ferramentas import AcervoPool
    from rag.agente import FontesPool
    from rag.embeddings import Embedder

    _, pool, _ = bancos
    fontes = FontesPool(pool, Embedder("int8"))
    acervo = AcervoPool(fontes, pool)
    pergunta = "quantas vezes posso trancar o curso"
    via_mcp = ferramentas.buscar_regulamento(acervo, pergunta)
    direto = fontes.buscar_regulamento(pergunta)
    assert [t.id for t in via_mcp.trechos] == [r.id for r in direto]
    documentos = {d.id: d for d in acervo.documentos()}
    assert documentos["rgcg"].trechos == 142 and documentos["calendario-2026"].eventos == 179
