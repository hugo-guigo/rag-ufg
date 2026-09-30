"""LLM como juiz: compara a resposta do assistente com a referência humana e checa se cada afirmação
está nos trechos citados.

O juiz é um modelo diferente e maior (gpt-oss-120b) que o que responde (gpt-oss-20b), para reduzir o
viés de um modelo aprovar o próprio estilo. Juiz também erra: as decisões ficam no CSV para revisão
humana por amostragem.
"""
from rag.llm import ClienteGroq, RespostaLLM

MODELO_JUIZ = "openai/gpt-oss-120b"
REFERENCIA_SEM_RESPOSTA = "O regulamento (RGCG) não trata disso."

SISTEMA = """Você avalia respostas de um assistente sobre o Regulamento Geral dos Cursos de Graduação (RGCG) da UFG.
Você recebe: a pergunta, uma resposta de referência escrita por uma pessoa, a resposta do assistente e os trechos do regulamento que o assistente citou.

Avalie:
- correta: "sim" se a resposta do assistente traz a informação essencial da referência sem contradizê-la; "parcial" se acerta só parte ou omite algo essencial; "nao" se contradiz a referência ou não responde. Se a referência diz que o regulamento não trata do assunto: "sim" se o assistente também diz que não trata (pode citar uma regra relacionada); "nao" se o assistente responde como se o regulamento tratasse.
- fiel: true se TODA afirmação factual da resposta do assistente está sustentada pelos trechos citados (paráfrase vale). Dizer que o regulamento não trata de algo não precisa de sustentação. Número de artigo, parágrafo, prazo ou percentual que não bate com os trechos conta como não sustentado. Sem trechos citados, qualquer afirmação sobre o conteúdo do regulamento é não sustentada.
- sem_suporte: as afirmações não sustentadas, copiadas da resposta (lista vazia se fiel).
- justificativa: uma frase curta."""

SCHEMA = {
    "type": "object",
    "properties": {
        "justificativa": {"type": "string"},
        "correta": {"type": "string", "enum": ["sim", "parcial", "nao"]},
        "fiel": {"type": "boolean"},
        "sem_suporte": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["justificativa", "correta", "fiel", "sem_suporte"],
    "additionalProperties": False,
}


# Etapa 5: o agente também cita eventos do calendário. Mesmos critérios, com as duas fontes.
REFERENCIA_SEM_RESPOSTA_AGENTE = "O regulamento (RGCG) e o calendário acadêmico não tratam disso."
SISTEMA_AGENTE = (SISTEMA
                  .replace("sobre o Regulamento Geral dos Cursos de Graduação (RGCG) da UFG.",
                           "sobre o Regulamento Geral dos Cursos de Graduação (RGCG) e o Calendário Acadêmico da UFG.")
                  .replace("os trechos do regulamento que o assistente citou", "os trechos do regulamento e os eventos do calendário que o assistente citou")
                  .replace("a referência diz que o regulamento não trata", "a referência diz que as fontes não tratam")
                  .replace("sobre o conteúdo do regulamento é não sustentada", "sobre o conteúdo das fontes é não sustentada")
                  .replace("Número de artigo, parágrafo, prazo ou percentual", "Número de artigo, parágrafo, data, prazo ou percentual")
                  .replace("sustentada pelos trechos citados", "sustentada pelas fontes citadas (trechos e eventos)")
                  .replace("não bate com os trechos", "não bate com as fontes"))


def julgar(cliente: ClienteGroq, pergunta: str, referencia: str, resposta: str,
           trechos_citados: list[tuple[str, str]], modelo: str = MODELO_JUIZ, sistema: str = SISTEMA) -> RespostaLLM:
    """trechos_citados: pares (rótulo, texto)."""
    citados = "\n\n".join(f"{rot}\n{texto}" for rot, texto in trechos_citados) or "(nenhum trecho citado)"
    conteudo = (f"Pergunta: {pergunta}\n\nResposta de referência: {referencia}\n\n"
                f"Resposta do assistente: {resposta}\n\nTrechos citados pelo assistente:\n\n{citados}")
    return cliente.json(modelo, [{"role": "system", "content": sistema}, {"role": "user", "content": conteudo}],
                        SCHEMA, "julgamento", max_tokens=600, estimativa_tokens=1800)
