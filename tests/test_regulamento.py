from rag.extrair import Linha, linhas_da_pagina
from rag.regulamento import juntar_linhas, paragrafos_rgcg


def linhas(*paginas: str) -> list[Linha]:
    resultado: list[Linha] = []
    for n, texto in enumerate(paginas, start=1):
        resultado += linhas_da_pagina(texto, n)
    return resultado


def test_remove_numero_da_pagina_so_na_primeira_linha():
    ls = linhas_da_pagina("7 \n \nArt. 20. Prazo de 7 dias.\n7", 7)
    assert [linha.texto for linha in ls] == ["", "", "Art. 20. Prazo de 7 dias.", "7"]


def test_juntar_linhas_hifen_incisos_e_espaco_antes_da_virgula():
    texto = juntar_linhas(["Art. 5º Os fundamentos teórico-", "metodológicos da UFG , e:", "I- um;", "II- dois."])
    assert texto == "Art. 5º Os fundamentos teórico-metodológicos da UFG, e:\nI- um;\nII- dois."


RESOLUCAO_E_ANEXO = (
    "RESOLUÇÃO\n\nArt. 1º Aprovar o regulamento.\n\nArt. 2º Entra em vigor.\n",
    "2\n\nTÍTULO I\nDAS DISPOSIÇÕES\nINICIAIS\n\nArt. 1º Os cursos conferirão grau.\n\n"
    "Parágrafo único. Os cursos poderão ter ênfases.\n\nCapítulo I\nDa Organização\n\n"
    "Art. 2º O semestre letivo compreende\n",
    "3\n\no período necessário.\n§ 1º Conforme o Capítulo III (Do Corpo Discente) do Regimento.\n\n"
    "CapítuloV\nDo Calendário\n\nArt. 3º Das V agas Remanescentes.\n",
)


def test_paragrafos_comecam_no_anexo_e_guardam_secao():
    ps = paragrafos_rgcg(linhas(*RESOLUCAO_E_ANEXO))
    assert ps[0].texto == "Art. 1º Os cursos conferirão grau."  # os artigos da resolução ficaram de fora
    assert ps[0].secao == "Título I: DAS DISPOSIÇÕES INICIAIS"
    assert ps[1].artigo == 1 and ps[1].texto.startswith("Parágrafo único.")
    assert ps[2].secao == "Título I: DAS DISPOSIÇÕES INICIAIS > Capítulo I: Da Organização"


def test_frase_cortada_pela_virada_de_pagina_continua_no_mesmo_paragrafo():
    ps = paragrafos_rgcg(linhas(*RESOLUCAO_E_ANEXO))
    art2 = [p for p in ps if p.artigo == 2]
    assert art2[0].texto == "Art. 2º O semestre letivo compreende o período necessário."
    assert art2[0].pagina == 2
    assert art2[1].texto.startswith("§ 1º") and art2[1].pagina == 3


def test_mencao_a_capitulo_no_meio_do_texto_nao_vira_cabecalho():
    ps = paragrafos_rgcg(linhas(*RESOLUCAO_E_ANEXO))
    assert "Capítulo III (Do Corpo Discente)" in ps[3].texto
    assert ps[3].secao.endswith("Capítulo I: Da Organização")


def test_capitulo_sem_espaco_zera_a_secao_e_corrige_artefato():
    ps = paragrafos_rgcg(linhas(*RESOLUCAO_E_ANEXO))
    assert ps[-1].secao == "Título I: DAS DISPOSIÇÕES INICIAIS > Capítulo V: Do Calendário"
    assert ps[-1].texto == "Art. 3º Das Vagas Remanescentes."
