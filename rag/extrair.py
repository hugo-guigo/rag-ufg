"""Extrai o texto dos PDFs linha a linha, guardando a página de cada linha (a página vai para a citação)."""
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


@dataclass(frozen=True)
class Linha:
    pagina: int
    texto: str  # sem espaços nas pontas; "" marca linha em branco


def linhas_da_pagina(texto: str, numero: int) -> list[Linha]:
    brutas = [linha.strip() for linha in texto.splitlines()]
    # O RGCG imprime o número da página na primeira linha. Sem remover, ele gruda no parágrafo seguinte.
    for i, linha in enumerate(brutas):
        if linha:
            if linha == str(numero):
                brutas[i] = ""
            break
    return [Linha(numero, linha) for linha in brutas]


def ler_linhas(pdf: Path) -> list[Linha]:
    linhas: list[Linha] = []
    for numero, pagina in enumerate(PdfReader(pdf).pages, start=1):
        linhas += linhas_da_pagina(pagina.extract_text() or "", numero)
    return linhas
