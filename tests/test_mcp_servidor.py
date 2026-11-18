"""Servidor MCP: ferramentas, contrato anunciado, erros e integração em stdio. Sem banco (acervo falso)."""
import json
import os
import sys
from datetime import date
from pathlib import Path

import anyio
import pytest
from mcp import Client, StdioServerParameters

from mcp_ufg import ferramentas
from mcp_ufg.servidor import criar_servidor
from rag.agente import ErroFerramenta
from tests.mcp_falso import AcervoFalso

RAIZ = Path(__file__).resolve().parent.parent
CONTRATO = RAIZ / "tests" / "dados" / "contrato_mcp.json"


def rodar(funcao, *args):
    return anyio.run(funcao, *args)


# ---- ferramentas, sem protocolo

def test_buscar_regulamento_converte_trechos_com_rotulo_e_paginas():
    r = ferramentas.buscar_regulamento(AcervoFalso(), "  quantas vezes posso trancar?  ", k=2)
    assert r.pergunta == "quantas vezes posso trancar?"
    assert [t.id for t in r.trechos] == ["rgcg-82", "rgcg-83"]
    assert r.trechos[0].rotulo == "RGCG, Art. 82, p. 25"
    assert r.trechos[1].paginas == "25-26"
    assert r.trechos[0].similaridade == 0.8123


def test_buscar_regulamento_recusa_pergunta_vazia_e_k_fora_da_faixa():
    with pytest.raises(ErroFerramenta, match="pergunta vazia"):
        ferramentas.buscar_regulamento(AcervoFalso(), "   ")
    with pytest.raises(ErroFerramenta, match="k deve estar entre 1 e 10"):
        ferramentas.buscar_regulamento(AcervoFalso(), "trancar", k=11)


def test_consultar_calendario_normaliza_semestre_e_valida_intervalo():
    acervo = AcervoFalso()
    r = ferramentas.consultar_calendario(acervo, "início do segundo semestre de 2026")
    assert r.termo == "início do 2026/2"
    assert acervo.chamadas[-1] == ("consultar_calendario", "início do 2026/2", None, None)
    assert [e.id for e in r.eventos] == [42, 41]  # em ordem de data
    assert r.eventos[1].rotulo == "Calendário 2026, 10/08/2026, p. 4"
    with pytest.raises(ErroFerramenta, match="anterior"):
        ferramentas.consultar_calendario(acervo, "aulas", date(2026, 9, 1), date(2026, 8, 1))
    with pytest.raises(ErroFerramenta, match="informe um termo"):
        ferramentas.consultar_calendario(acervo, "", date(2026, 9, 1), None)


# ---- pelo protocolo (cliente em processo)

def _contrato(servidor) -> dict:
    async def ler():
        async with Client(servidor) as cliente:
            tools = (await cliente.list_tools()).tools
            recursos = (await cliente.list_resources()).resources
        return {
            "ferramentas": [t.model_dump(mode="json", exclude_none=True, by_alias=True) for t in tools],
            "recursos": [r.model_dump(mode="json", exclude_none=True, by_alias=True) for r in recursos],
        }
    return rodar(ler)


def test_contrato_anunciado_igual_ao_registrado():
    """O que o servidor anuncia (nomes, descrições, schemas de entrada e saída) é o contrato com os
    clientes. Mudou sem querer, o teste falha; mudou de propósito, rode com ATUALIZAR_CONTRATO=1."""
    atual = _contrato(criar_servidor(AcervoFalso()))
    if os.environ.get("ATUALIZAR_CONTRATO") == "1":
        CONTRATO.write_text(json.dumps(atual, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert atual == json.loads(CONTRATO.read_text(encoding="utf-8"))


def test_contrato_tem_as_ferramentas_so_de_leitura_com_entrada_e_saida_tipadas():
    contrato = _contrato(criar_servidor(AcervoFalso()))
    por_nome = {t["name"]: t for t in contrato["ferramentas"]}
    assert set(por_nome) == {"buscar_regulamento", "consultar_calendario"}
    for t in por_nome.values():
        assert t["annotations"]["readOnlyHint"] is True
        assert t["description"].strip()
        assert "outputSchema" in t
    busca = por_nome["buscar_regulamento"]
    assert busca["inputSchema"]["required"] == ["pergunta"]
    assert {"minimum": 1, "maximum": 10, "default": 5}.items() <= busca["inputSchema"]["properties"]["k"].items()
    assert "trechos" in busca["outputSchema"]["properties"]
    assert "eventos" in por_nome["consultar_calendario"]["outputSchema"]["properties"]
    assert [r["uri"] for r in contrato["recursos"]] == ["ufg://fontes"]


def _chamar(servidor, nome: str, argumentos: dict):
    async def chamar():
        async with Client(servidor) as cliente:
            return await cliente.call_tool(nome, argumentos)
    return rodar(chamar)


def test_chamada_devolve_conteudo_estruturado():
    r = _chamar(criar_servidor(AcervoFalso()), "buscar_regulamento", {"pergunta": "trancar", "k": 1})
    assert not r.is_error
    assert r.structured_content["trechos"][0]["rotulo"] == "RGCG, Art. 82, p. 25"


def test_erro_corrigivel_volta_para_o_modelo_com_a_mensagem():
    r = _chamar(criar_servidor(AcervoFalso()), "consultar_calendario",
                {"termo": "aulas", "data_inicio": "2026-09-01", "data_fim": "2026-08-01"})
    assert r.is_error
    assert "data_fim é anterior a data_inicio" in r.content[0].text


def test_argumento_fora_do_schema_e_recusado_antes_da_busca():
    acervo = AcervoFalso()
    r = _chamar(criar_servidor(acervo), "buscar_regulamento", {"pergunta": "trancar", "k": 50})
    assert r.is_error
    assert acervo.chamadas == []


def test_erro_interno_nao_vaza_detalhe_do_banco():
    acervo = AcervoFalso(erro=RuntimeError("senha=segredo host=neon"))
    r = _chamar(criar_servidor(acervo), "buscar_regulamento", {"pergunta": "trancar"})
    assert r.is_error
    assert "falha interna (RuntimeError)" in r.content[0].text
    assert "segredo" not in r.content[0].text


def test_timeout_por_ferramenta():
    r = _chamar(criar_servidor(AcervoFalso(atraso=1.0), timeout=0.2), "buscar_regulamento", {"pergunta": "trancar"})
    assert r.is_error
    assert "passou de" in r.content[0].text


def test_recurso_lista_as_fontes():
    async def ler():
        async with Client(criar_servidor(AcervoFalso())) as cliente:
            return await cliente.read_resource("ufg://fontes")
    conteudo = json.loads(rodar(ler).contents[0].text)
    assert {"id": "rgcg", "trechos": 142}.items() <= conteudo[0].items()


# ---- integração cliente-servidor em stdio: subprocesso e protocolo de verdade

def test_stdio_de_ponta_a_ponta():
    parametros = StdioServerParameters(
        command=sys.executable, args=[str(RAIZ / "tests" / "mcp_falso.py")],
        env={**os.environ, "PYTHONPATH": str(RAIZ)}, cwd=str(RAIZ))

    async def conversar():
        async with Client(parametros) as cliente:
            nomes = sorted(t.name for t in (await cliente.list_tools()).tools)
            r = await cliente.call_tool("consultar_calendario", {"termo": "segundo semestre de 2026"})
            return nomes, r
    nomes, r = rodar(conversar)
    assert nomes == ["buscar_regulamento", "consultar_calendario"]
    assert not r.is_error
    assert r.structured_content["termo"] == "2026/2"
    assert len(r.structured_content["eventos"]) == 2


# ---- rastreio de cada chamada

def test_rastreio_registra_a_chamada_sem_o_texto_da_pergunta():
    from mcp_ufg.rastreio import Rastreio

    gravados: list[dict] = []

    def gravar_falhando(registro):  # a primeira gravação falha: a chamada não pode cair por isso
        gravados.append(registro)
        if len(gravados) == 1:
            raise RuntimeError("banco fora")

    async def chamar():
        async with Client(criar_servidor(AcervoFalso(), middleware=[Rastreio(gravar_falhando)])) as cliente:
            ok = await cliente.call_tool("buscar_regulamento", {"pergunta": "posso trancar o curso?", "k": 2},
                                         meta={"rastreio": "pergunta-1"})
            erro = await cliente.call_tool("consultar_calendario", {"termo": "x", "data_inicio": "2026-09-01",
                                                                    "data_fim": "2026-01-01"})
            return ok, erro
    ok, erro = rodar(chamar)
    assert not ok.is_error and erro.is_error
    primeiro, segundo = gravados
    esperado = {"evento": "mcp.ferramenta", "rastreio": "pergunta-1", "cliente": "local",
                "ferramenta": "buscar_regulamento", "argumentos": {"pergunta_chars": 22, "k": 2}, "ok": True, "erro": None}
    assert esperado.items() <= primeiro.items()
    assert primeiro["bytes"] > 0
    assert "posso trancar" not in json.dumps(gravados, ensure_ascii=False)
    assert segundo["ok"] is False and len(segundo["rastreio"]) == 32  # criado no servidor
