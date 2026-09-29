"""Transforma as linhas do RGCG em parágrafos com artigo, seção e página.

O regulamento tem estrutura jurídica: Título > Capítulo > Seção > Art. > § / incisos. Guardar essa
estrutura permite dividir o texto por artigo e citar "Art. 65, p. 21" na resposta.
"""
import re
from dataclasses import dataclass

from rag.extrair import Linha

RE_CABECALHO = re.compile(r"^(TÍTULO|Capítulo|Seção)\s*([IVXLC]+)$")
RE_ARTIGO = re.compile(r"^Art\.\s*(\d+)")
RE_INICIO_PARAGRAFO = re.compile(r"^(Art\.\s*\d+|§|Parágrafo único)")
RE_ITEM = re.compile(r"^([IVXLC]+\s*[-–]|[a-z]\))")
NIVEL = {"TÍTULO": 0, "Capítulo": 1, "Seção": 2}
# Erros de extração do pypdf conferidos à mão no PDF (letra separada por kerning).
ARTEFATOS = [("V agas", "Vagas")]


@dataclass(frozen=True)
class Paragrafo:
    texto: str
    pagina: int
    artigo: int | None
    secao: str  # ex.: "Título II > Capítulo III > Seção III: Do Cancelamento e do Acréscimo ..."


def juntar_linhas(linhas: list[str]) -> str:
    texto = linhas[0]
    for linha in linhas[1:]:
        if RE_ITEM.match(linha):
            texto += "\n" + linha  # inciso (I-, II-) ou alínea (a)) fica em linha própria
        elif texto.endswith("-") and linha[:1].islower():
            texto += linha  # "teórico-" + "metodológicos": o hífen é da palavra, só some a quebra
        else:
            texto += " " + linha
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r" ([,.;:])", r"\1", texto)  # "UFG , deve" -> "UFG, deve"
    for errado, certo in ARTEFATOS:
        texto = texto.replace(errado, certo)
    return texto.strip()


def formatar_secao(niveis: list[str | None]) -> str:
    return " > ".join(n for n in niveis if n)


def continua_na_proxima_pagina(linhas: list[Linha], i: int, atual: list[str], pagina_ultima: int) -> bool:
    """Linha em branco que é só a virada de página, com a frase cortada no meio, não fecha o parágrafo."""
    if not atual or atual[-1].endswith((".", ";", ":")):
        return False
    j = i
    while j < len(linhas) and not linhas[j].texto:
        j += 1
    if j == len(linhas) or linhas[j].pagina == pagina_ultima:
        return False
    proxima = linhas[j].texto
    return not (RE_INICIO_PARAGRAFO.match(proxima) or RE_CABECALHO.match(proxima) or RE_ITEM.match(proxima))


def paragrafos_rgcg(linhas: list[Linha]) -> list[Paragrafo]:
    # A página 1 é a resolução que aprova o regulamento. Ela tem Art. 1º e 2º próprios, que colidiriam
    # com os do anexo; o regulamento começa no primeiro TÍTULO.
    inicio = next(i for i, linha in enumerate(linhas) if RE_CABECALHO.match(linha.texto))
    paragrafos: list[Paragrafo] = []
    niveis: list[str | None] = [None, None, None]
    artigo: int | None = None
    atual: list[str] = []
    pagina = pagina_ultima = 0

    def fechar() -> None:
        nonlocal atual
        if atual:
            paragrafos.append(Paragrafo(juntar_linhas(atual), pagina, artigo, formatar_secao(niveis)))
            atual = []

    i = inicio
    while i < len(linhas):
        linha = linhas[i]
        cabecalho = RE_CABECALHO.match(linha.texto)
        if cabecalho:
            fechar()
            nome: list[str] = []
            i += 1
            while i < len(linhas) and linhas[i].texto:  # o nome da seção vai até a linha em branco
                nome.append(linhas[i].texto)
                i += 1
            nivel = NIVEL[cabecalho.group(1)]
            rotulo = cabecalho.group(1).capitalize()
            niveis[nivel] = f"{rotulo} {cabecalho.group(2)}: {juntar_linhas(nome)}" if nome else f"{rotulo} {cabecalho.group(2)}"
            for mais_fundo in range(nivel + 1, len(niveis)):
                niveis[mais_fundo] = None
            continue
        if not linha.texto:
            if not continua_na_proxima_pagina(linhas, i, atual, pagina_ultima):
                fechar()
        else:
            if RE_INICIO_PARAGRAFO.match(linha.texto):
                fechar()
            artigo_novo = RE_ARTIGO.match(linha.texto)
            if artigo_novo:
                artigo = int(artigo_novo.group(1))
            if not atual:
                pagina = linha.pagina
            atual.append(linha.texto)
            pagina_ultima = linha.pagina
        i += 1
    fechar()
    return paragrafos
