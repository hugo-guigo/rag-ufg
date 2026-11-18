"""Acervo falso para os testes do MCP (sem banco) e servidor stdio sobre ele.

Rodado como script, sobe o servidor MCP de verdade em stdio com este acervo: é o processo que o teste
de integração cliente-servidor lança.
"""
import time
from datetime import date

from mcp_ufg.ferramentas import Documento
from rag.busca import Evento, Resultado

TRECHOS = [
    Resultado("rgcg-82", "rgcg", "Art. 82. O estudante poderá trancar a matrícula no curso...",
              "Capítulo VI > Seção II > Art. 82", (82,), 25, 25, 0.81234),
    Resultado("rgcg-83", "rgcg", "Art. 83. O trancamento não poderá exceder...",
              "Capítulo VI > Seção II > Art. 83", (83,), 25, 26, 0.79),
    Resultado("rgcg-12", "rgcg", "Art. 12. A frequência mínima...", "", (12,), 7, 7, 0.5),
]
EVENTOS = [
    Evento(41, date(2026, 8, 10), date(2026, 8, 10), "Início das aulas de 2026/2 da Graduação", 4),
    Evento(42, date(2026, 8, 3), date(2026, 8, 21), "Trancamento de matrícula 2026/2", 4),
]


class AcervoFalso:
    def __init__(self, atraso: float = 0.0, erro: Exception | None = None):
        self.atraso, self.erro = atraso, erro
        self.chamadas: list[tuple] = []

    def _talvez_falhar(self):
        if self.atraso:
            time.sleep(self.atraso)
        if self.erro:
            raise self.erro

    def buscar_regulamento(self, consulta, k=None):
        self.chamadas.append(("buscar_regulamento", consulta, k))
        self._talvez_falhar()
        return TRECHOS[: k or 5]

    def consultar_calendario(self, termo, inicio, fim):
        self.chamadas.append(("consultar_calendario", termo, inicio, fim))
        self._talvez_falhar()
        return sorted(EVENTOS, key=lambda e: e.data_inicio)

    def documentos(self):
        self._talvez_falhar()
        return [Documento(id="rgcg", titulo="RGCG", url="https://exemplo/rgcg.pdf", sha256="a" * 64,
                          trechos=142, eventos=0)]


if __name__ == "__main__":
    from mcp_ufg.servidor import criar_servidor

    criar_servidor(AcervoFalso()).run("stdio")
