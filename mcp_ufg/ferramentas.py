"""As ferramentas do servidor MCP, sem nada do protocolo: validação e conversão para modelos Pydantic.

A busca é a mesma da API (rag.busca, pelas mesmas classes de fontes do agente). Este módulo só
confere os argumentos e transforma Resultado e Evento em modelos com schema, que o servidor anuncia
como outputSchema. Separado do servidor para ser testado sem MCP nenhum.
"""
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from pydantic import BaseModel, Field

from rag.agente import ErroFerramenta, rotulo_evento, validar_calendario
from rag.busca import Evento, Resultado
from rag.resposta import rotulo

K_PADRAO = 5
K_MAXIMO = 10


class Trecho(BaseModel):
    id: str = Field(description="Identificador estável do trecho no índice.")
    rotulo: str = Field(description="Como citar: documento, artigo e página. Ex.: RGCG, Art. 82, p. 25.")
    artigos: list[int] = Field(description="Números dos artigos que o trecho contém.")
    paginas: str = Field(description="Página ou intervalo de páginas no PDF oficial.")
    texto: str = Field(description="Texto do trecho, como está no regulamento.")
    similaridade: float = Field(description="Cosseno entre a pergunta e o trecho (0 a 1; maior é mais parecido).")


class ResultadoRegulamento(BaseModel):
    pergunta: str
    trechos: list[Trecho] = Field(description="Do mais parecido para o menos parecido.")


class EventoCalendario(BaseModel):
    id: int
    rotulo: str = Field(description="Como citar: calendário, datas e página.")
    data_inicio: date
    data_fim: date
    descricao: str
    pagina: int


class ResultadoCalendario(BaseModel):
    termo: str = Field(description="O termo usado na busca, depois da normalização de semestre (ex.: 2026/2).")
    eventos: list[EventoCalendario] = Field(description="Em ordem de data.")


class Documento(BaseModel):
    id: str
    titulo: str
    url: str
    sha256: str
    trechos: int = Field(description="Trechos do documento no índice do regulamento.")
    eventos: int = Field(description="Eventos do documento na tabela do calendário.")


class Acervo(Protocol):
    """O que as ferramentas consultam. A implementação real usa o pool do Postgres; os testes, uma falsa."""

    def buscar_regulamento(self, consulta: str, k: int | None = None) -> list[Resultado]: ...

    def consultar_calendario(self, termo: str, inicio: date | None, fim: date | None) -> list[Evento]: ...

    def documentos(self) -> list[Documento]: ...


def buscar_regulamento(acervo: Acervo, pergunta: str, k: int = K_PADRAO) -> ResultadoRegulamento:
    pergunta = pergunta.strip()
    if not pergunta:
        raise ErroFerramenta("pergunta vazia: passe a dúvida do estudante com as palavras dele")
    if not 1 <= k <= K_MAXIMO:
        raise ErroFerramenta(f"k deve estar entre 1 e {K_MAXIMO}")
    resultados = acervo.buscar_regulamento(pergunta, k)
    return ResultadoRegulamento(pergunta=pergunta, trechos=[_trecho(r) for r in resultados])


def consultar_calendario(acervo: Acervo, termo: str = "", data_inicio: date | None = None,
                         data_fim: date | None = None) -> ResultadoCalendario:
    termo = validar_calendario(termo, data_inicio, data_fim)
    eventos = acervo.consultar_calendario(termo, data_inicio, data_fim)
    return ResultadoCalendario(termo=termo, eventos=[_evento(e) for e in eventos])


def _trecho(r: Resultado) -> Trecho:
    paginas = str(r.pagina_inicio) if r.pagina_inicio == r.pagina_fim else f"{r.pagina_inicio}-{r.pagina_fim}"
    return Trecho(id=r.id, rotulo=rotulo(r), artigos=list(r.artigos), paginas=paginas, texto=r.texto,
                  similaridade=round(r.similaridade, 4))


def _evento(e: Evento) -> EventoCalendario:
    return EventoCalendario(id=e.id, rotulo=rotulo_evento(e), data_inicio=e.data_inicio, data_fim=e.data_fim,
                            descricao=e.descricao, pagina=e.pagina)


SQL_DOCUMENTOS = """
    SELECT d.id, d.titulo, d.url, d.sha256,
           (SELECT count(*) FROM trechos t WHERE t.documento = d.id AND t.estrategia = 'artigo_secao'
              AND t.modelo = %(m)s)::int,
           (SELECT count(*) FROM eventos_calendario e WHERE e.documento = d.id)::int
    FROM documentos d ORDER BY d.id"""


@dataclass
class AcervoPool:
    """O acervo real: as fontes do agente (FontesPool) mais a lista de documentos, no mesmo pool."""

    fontes: object  # rag.agente.FontesPool
    pool: object

    def buscar_regulamento(self, consulta: str, k: int | None = None) -> list[Resultado]:
        return self.fontes.buscar_regulamento(consulta, k)

    def consultar_calendario(self, termo: str, inicio: date | None, fim: date | None) -> list[Evento]:
        return self.fontes.consultar_calendario(termo, inicio, fim)

    def documentos(self) -> list[Documento]:
        with self.pool.connection() as conexao:
            linhas = conexao.execute(SQL_DOCUMENTOS, {"m": self.fontes.embedder.nome}).fetchall()
        return [Documento(id=r[0], titulo=r[1], url=r[2], sha256=r[3], trechos=r[4], eventos=r[5]) for r in linhas]
