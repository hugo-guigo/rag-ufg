from datetime import date

from rag.calendario import Evento, eventos_do_calendario, gravar_csv, ler_csv
from rag.extrair import Linha


def linhas(texto: str, pagina: int = 8) -> list[Linha]:
    return [Linha(pagina, linha.strip()) for linha in texto.splitlines()]


def resumo(eventos: list[Evento]) -> list[tuple[str, str, str]]:
    return [(e.data_inicio.isoformat(), e.data_fim.isoformat(), e.descricao) for e in eventos]


def test_formatos_de_data_do_pdf():
    evs = eventos_do_calendario(linhas("""JANEIRO/2026
S T Q Q S S D
05/01 a
28/02 Período de verão (2025/4)
DATA EVENTOS
01/01 Feriado: Confraternização universal.
01/12/25
a
26/01/26
Solicitação de oferta de turma: Período para as
coordenações de curso.
05/01 a
23/01
Solicitação de cadastro de NL: Período para
2026/1.
16 e 17 Carnaval.
De 9 a 13 Evento: CONPEEX.
05/08/ a
06/08
Análise: texto.
Anexo à Resolução CEPEC/UFG nº 1966/2025 (5798611) SEI / pg. 8"""))
    assert resumo(evs) == [
        ("2026-01-01", "2026-01-01", "Feriado: Confraternização universal."),
        ("2025-12-01", "2026-01-26", "Solicitação de oferta de turma: Período para as coordenações de curso."),
        ("2026-01-05", "2026-01-23", "Solicitação de cadastro de NL: Período para 2026/1."),
        ("2026-01-16", "2026-01-17", "Carnaval."),
        ("2026-01-09", "2026-01-13", "Evento: CONPEEX."),
        ("2026-08-05", "2026-08-06", "Análise: texto."),
    ]
    assert evs[0].categoria == "Feriado" and evs[3].categoria is None


def test_quadro_resumo_depois_de_data_eventos_e_ignorado():
    evs = eventos_do_calendario(linhas("""MARÇO/2026
DATA EVENTOS
S T Q Q S S D
1
2 3 4 5 6 7 8
2 Início das aulas 2026/1
13 e
14
Espaço das Profissões
02/03 Período de aulas: Início das aulas.
13 a
16/10
XIII CONEPEC."""))
    assert resumo(evs) == [("2026-03-02", "2026-03-02", "Período de aulas: Início das aulas."),
                           ("2026-10-13", "2026-10-16", "XIII CONEPEC.")]


def test_intervalo_que_atravessa_o_ano_e_evento_repetido():
    evs = eventos_do_calendario(linhas("""DEZEMBRO/2026
DATA EVENTOS
21/12 a
11/01
Oferta de turma: para 2027/1.
30/11 e
01/12
Colóquio.
30/11 e
01/12
Colóquio."""))
    assert resumo(evs) == [("2026-12-21", "2027-01-11", "Oferta de turma: para 2027/1."),
                           ("2026-11-30", "2026-12-01", "Colóquio.")]


def test_csv_ida_e_volta(tmp_path):
    ev = [Evento(date(2026, 3, 2), date(2026, 3, 2), "Período de aulas: início, 2026/1.", "Período de aulas", 10)]
    gravar_csv(ev, tmp_path / "c.csv")
    assert ler_csv(tmp_path / "c.csv") == ev
