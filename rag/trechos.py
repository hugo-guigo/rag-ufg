"""Duas estratégias de chunking para comparar na avaliação.

- por_artigo: usa a estrutura do regulamento. Cada artigo vira um trecho; artigo longo é dividido
  entre parágrafos (§), nunca no meio de um. A seção entra no texto que vira embedding.
- por_janela: ignora a estrutura. Janelas de tamanho fixo em caracteres, com sobreposição, cortadas
  em espaço em branco. É a linha de base mais comum em tutoriais de RAG.

Os dois guardam quais artigos cada trecho cobre, para medir recall@k com a mesma régua.
"""
from dataclasses import dataclass
from itertools import groupby

from rag.regulamento import Paragrafo


@dataclass(frozen=True)
class Trecho:
    id: str
    documento: str
    estrategia: str
    texto: str  # o que aparece na citação
    contexto: str  # seção e artigo; vai junto no embedding, não na citação
    artigos: tuple[int, ...]
    pagina_inicio: int
    pagina_fim: int

    def texto_para_embedding(self) -> str:
        return f"{self.contexto}\n{self.texto}" if self.contexto else self.texto


def por_artigo(paragrafos: list[Paragrafo], documento: str = "rgcg", max_chars: int = 1500) -> list[Trecho]:
    trechos: list[Trecho] = []
    com_artigo = [p for p in paragrafos if p.artigo is not None]
    for artigo, grupo in groupby(com_artigo, key=lambda p: p.artigo):
        partes = empacotar(list(grupo), max_chars)
        for k, parte in enumerate(partes, start=1):
            sufixo = f" (parte {k} de {len(partes)})" if len(partes) > 1 else ""
            trechos.append(Trecho(
                id=f"{documento}-art{artigo:03d}" + (f"-p{k}" if len(partes) > 1 else ""),
                documento=documento,
                estrategia="artigo",
                texto="\n".join(p.texto for p in parte),
                contexto=f"{parte[0].secao} > Art. {artigo}{sufixo}",
                artigos=(artigo,),
                pagina_inicio=parte[0].pagina,
                pagina_fim=parte[-1].pagina,
            ))
    return trechos


def empacotar(paragrafos: list[Paragrafo], max_chars: int) -> list[list[Paragrafo]]:
    """Agrupa parágrafos em ordem até max_chars. Um parágrafo maior que o limite fica sozinho."""
    partes: list[list[Paragrafo]] = []
    atual: list[Paragrafo] = []
    tamanho = 0
    for p in paragrafos:
        extra = len(p.texto) + (1 if atual else 0)
        if atual and tamanho + extra > max_chars:
            partes.append(atual)
            atual, tamanho, extra = [], 0, len(p.texto)
        atual.append(p)
        tamanho += extra
    if atual:
        partes.append(atual)
    return partes


def por_janela(paragrafos: list[Paragrafo], documento: str = "rgcg",
               tamanho: int = 800, sobreposicao: int = 150) -> list[Trecho]:
    if not 0 <= sobreposicao < tamanho // 2:
        raise ValueError("a sobreposição precisa ser menor que metade do tamanho")
    texto = ""
    spans: list[tuple[int, int, Paragrafo]] = []
    for p in paragrafos:
        if texto:
            texto += "\n"
        spans.append((len(texto), len(texto) + len(p.texto), p))
        texto += p.texto

    trechos: list[Trecho] = []
    inicio = 0
    while inicio < len(texto):
        fim = min(inicio + tamanho, len(texto))
        if fim < len(texto):
            corte = max(texto.rfind(" ", inicio, fim), texto.rfind("\n", inicio, fim))
            if corte > inicio + tamanho // 2:
                fim = corte
        cobertos = [p for a, b, p in spans if a < fim and b > inicio]
        trechos.append(Trecho(
            id=f"{documento}-jan{len(trechos) + 1:03d}",
            documento=documento,
            estrategia=f"janela{tamanho}",
            texto=texto[inicio:fim].strip(),
            contexto="",
            artigos=tuple(sorted({p.artigo for p in cobertos if p.artigo is not None})),
            pagina_inicio=min(p.pagina for p in cobertos),
            pagina_fim=max(p.pagina for p in cobertos),
        ))
        if fim == len(texto):
            break
        proximo = fim - sobreposicao
        espaco = texto.find(" ", proximo, fim)  # começa numa palavra inteira
        inicio = espaco + 1 if espaco != -1 else proximo
    return trechos
