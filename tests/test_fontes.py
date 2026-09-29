import hashlib

import pytest

import rag.fontes as fontes
from rag.fontes import Fonte, baixar, carregar_fontes


def test_fontes_json_tem_ids_unicos_e_checksum():
    fs = carregar_fontes()
    assert len({f.id for f in fs}) == len(fs)
    assert all(len(f.sha256) == 64 and f.url.startswith("https://") for f in fs)


def test_baixar_confere_o_checksum(tmp_path, monkeypatch):
    monkeypatch.setattr(fontes, "PASTA_PDFS", tmp_path / "pdfs")
    origem = tmp_path / "origem.pdf"
    origem.write_bytes(b"%PDF-1.4 teste")
    certo = hashlib.sha256(origem.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="difere do esperado"):
        baixar(Fonte("doc", "Doc", origem.as_uri(), "0" * 64))
    assert not (tmp_path / "pdfs" / "doc.pdf").exists()

    caminho = baixar(Fonte("doc", "Doc", origem.as_uri(), certo))
    assert caminho.read_bytes() == b"%PDF-1.4 teste"
