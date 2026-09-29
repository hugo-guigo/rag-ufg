"""Extrai os eventos do calendário acadêmico (anexo da Resolução CEPEC 1966/2025) para linhas de tabela.

Cada mês do PDF tem um quadro-resumo e uma lista "DATA EVENTOS". Só a lista é lida: o quadro repete os
mesmos eventos com menos detalhe. O PDF tem datas escritas de vários jeitos ("08/06 a" + quebra +
"10/07", "13 a 16/10", "De 9 a 13", "05/08/ a", "01/12/25 a 26/01/26"), então o parser gera um
CSV candidato que é revisado à mão. O CSV revisado (dados/calendario_2026.csv) é a fonte da verdade.
"""
import csv
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from rag.extrair import Linha

MESES = ["JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO", "JULHO", "AGOSTO",
         "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"]
RE_MES = re.compile(rf"^({'|'.join(MESES)})/(\d{{4}})")
DATA = r"(\d{1,2})(?:/(\d{1,2}))?(?:/(\d{2}|\d{4}))?/?"
RE_INICIO = re.compile(rf"^(?:De\s+)?{DATA}(?=\s|$)\s*(?:(a|e)(?=\s|$)\s*(?:{DATA}(?=\s|$))?)?\s*(.*)$")
RE_SO_DATA = re.compile(rf"^{DATA}(?=\s|$)\s*(.*)$")
RE_GRADE = re.compile(r"^(S T Q Q S S D|[\d ]+)$")  # cabeçalho e linhas de dias do minicalendário
RODAPE = "Anexo à Resolução"


@dataclass(frozen=True)
class Evento:
    data_inicio: date
    data_fim: date
    descricao: str
    categoria: str | None
    pagina: int


def _ano(texto: str | None, padrao: int) -> int:
    if not texto:
        return padrao
    return 2000 + int(texto) if len(texto) == 2 else int(texto)


def _categoria(descricao: str) -> str | None:
    antes, _, depois = descricao.partition(":")
    return antes.strip() if depois and len(antes) <= 60 else None


def eventos_do_calendario(linhas: list[Linha]) -> list[Evento]:
    eventos: list[Evento] = []
    mes = ano = 0
    na_lista = no_quadro = False
    atual: dict | None = None

    def fechar() -> None:
        nonlocal atual
        if atual and atual["texto"]:
            descricao = re.sub(r"\s+", " ", " ".join(atual["texto"])).strip()
            ev = Evento(atual["inicio"], atual["fim"], descricao, _categoria(descricao), atual["pagina"])
            if ev not in eventos:  # o PDF repete alguns eventos (ex.: Colóquio em nov e dez)
                eventos.append(ev)
        atual = None

    i = 0
    while i < len(linhas):
        texto, pagina = linhas[i].texto, linhas[i].pagina
        i += 1
        cabecalho_mes = RE_MES.match(texto)
        if cabecalho_mes:
            fechar()
            mes, ano = MESES.index(cabecalho_mes.group(1)) + 1, int(cabecalho_mes.group(2))
            na_lista = no_quadro = False
            continue
        if texto == "DATA EVENTOS":
            fechar()
            na_lista, no_quadro = True, False
            continue
        if RE_GRADE.match(texto):
            if na_lista:
                # Quando "DATA EVENTOS" cai no fim da página, o quadro-resumo do mês aparece depois dele.
                # O quadro usa só o dia ("2 Início das aulas"); a lista volta na primeira data com barra.
                fechar()
                no_quadro = True
            continue
        if not na_lista or not texto or texto.startswith(RODAPE):
            continue
        m = RE_INICIO.match(texto)
        if no_quadro:
            if not (m and "/" in texto.split()[0]):
                continue
            no_quadro = False
        if not m:
            if atual:
                atual["texto"].append(texto)
            continue
        fechar()
        d1, m1, a1, conector, d2, m2, a2, resto = m.groups()
        if not conector and not resto and i < len(linhas) and linhas[i].texto in ("a", "e"):
            conector = linhas[i].texto  # "01/12/25", "a" e "26/01/26" em três linhas
            i += 1
        if conector and not d2 and i < len(linhas):
            # "08/06 a" e a data final na linha seguinte, às vezes com o texto junto
            seguinte = RE_SO_DATA.match(linhas[i].texto)
            if seguinte:
                d2, m2, a2, resto = seguinte.groups()
                i += 1
        mes_fim = int(m2) if m2 else (int(m1) if m1 else mes)
        mes_inicio = int(m1) if m1 else mes_fim
        inicio = date(_ano(a1, ano), mes_inicio, int(d1))
        fim = date(_ano(a2, inicio.year), mes_fim, int(d2)) if d2 else inicio
        if fim < inicio and not a2:
            fim = fim.replace(year=fim.year + 1)  # "21/12 a 11/01" atravessa o ano
        atual = {"inicio": inicio, "fim": fim, "pagina": pagina, "texto": [resto] if resto else []}
    fechar()
    return eventos


CAMPOS = ["data_inicio", "data_fim", "descricao", "categoria", "pagina"]


def gravar_csv(eventos: list[Evento], caminho: Path) -> None:
    with open(caminho, "w", encoding="utf-8", newline="") as saida:
        escritor = csv.writer(saida)
        escritor.writerow(CAMPOS)
        for e in sorted(eventos, key=lambda e: (e.data_inicio, e.data_fim, e.descricao)):
            escritor.writerow([e.data_inicio.isoformat(), e.data_fim.isoformat(), e.descricao,
                               e.categoria or "", e.pagina])


def ler_csv(caminho: Path) -> list[Evento]:
    with open(caminho, encoding="utf-8", newline="") as entrada:
        return [Evento(date.fromisoformat(r["data_inicio"]), date.fromisoformat(r["data_fim"]),
                       r["descricao"], r["categoria"] or None, int(r["pagina"]))
                for r in csv.DictReader(entrada)]
