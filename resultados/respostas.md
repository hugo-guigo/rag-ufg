# Avaliação das respostas (busca + LLM), conjunto avaliacao

Gerado por scripts/avaliar_respostas.py. Modelo das respostas: openai/gpt-oss-20b. Juiz: openai/gpt-oss-120b. Busca: artigo com seção, vetorial, e5-small int8.

| Métrica | k=3 | k=5 |
|---|---|---|
| Perguntas (com resposta / sem) | 32 / 8 | 32 / 8 |
| Trecho certo entre os recuperados | 26/32 (81%) | 29/32 (91%) |
| Correta, com resposta (juiz: sim) | 22/32 (69%) | 23/32 (72%) |
| Correta ou parcial, com resposta | 27/32 (84%) | 29/32 (91%) |
| Citação correta (trecho anotado citado) | 26/32 (81%) | 28/32 (88%) |
| Fiel às fontes citadas (juiz) | 28/30 (93%) | 28/30 (93%) |
| "Não sei" correto, estrito (cobertura nenhuma) | 8/8 (100%) | 8/8 (100%) |
| "Não sei" correto, tolerante (nenhuma ou parcial) | 8/8 (100%) | 8/8 (100%) |
| Sem resposta julgadas corretas (juiz) | 8/8 (100%) | 8/8 (100%) |
| Falso "não sei" (tinha resposta) | 2/32 (6%) | 2/32 (6%) |
| Citações inválidas | 0 | 0 |
| Chamadas refeitas por JSON cortado | 0 | 0 |
| Latência p50 / p95 (ms) | 530 / 922 | 558 / 1280 |
| Tokens por pergunta (entrada / saída) | 905 / 104 | 1263 / 105 |
| Custo por pergunta no plano pago (US$) | 0.000099 | 0.000126 |
| Custo por 1.000 perguntas (US$) | 0.10 | 0.13 |

Latência = embedding + busca + chamada ao LLM, sem as esperas para respeitar o limite por minuto do plano grátis. Custo só do modelo de resposta (o juiz é custo da avaliação, não do uso).

## Respostas marcadas pelo juiz (correta = nao, ou não fiel)

- k=3 r03 (parcial, correta=nao, fiel=False): A resposta contradiz a referência, que indica limite de 4 semestres, e não há suporte nos trechos citados para a afirmação de ausência de limite. Sem suporte: O regulamento não estabelece um limite máximo de vezes que um estudante pode trancar a matrícula durante o curso.; não menciona quantidade máxima..
- k=3 r09 (nenhuma, correta=nao, fiel=False): A referência indica que o regulamento permite contestação em até 5 dias, contradizendo a afirmação do assistente. Sem suporte: O regulamento não trata da possibilidade de contestar faltas lançadas pelo professor..
- k=3 r12 (nenhuma, correta=nao, fiel=False): A referência indica que o regulamento especifica situações de jubilamento, mas o assistente afirma que não trata do tema. Sem suporte: O regulamento não trata sobre situações de jubilamento da UFG..
- k=3 r19 (total, correta=nao, fiel=False): A resposta não apresenta a fórmula correta do IP indicada na referência e inclui informações não suportadas pelo regulamento citado. Sem suporte: O índice de prioridade (IP) é calculado a partir dos valores de TI, TA e outros critérios de desempate listados no Art. 55, considerando, em ordem, maior TA, maior TI, menor QR, maior média relativa, maior média global e maior porcentual médio de frequência..
- k=3 r30 (total, correta=nao, fiel=True): A resposta cita o §7, que exige divulgação antes da próxima avaliação, mas a referência exige 4 dias antes (§6), portanto a informação essencial está incorreta.
- k=5 r09 (nenhuma, correta=nao, fiel=False): A referência indica que o regulamento permite contestação em até 5 dias, contradizendo a afirmação do assistente. Sem suporte: O regulamento não trata da possibilidade de contestar faltas lançadas pelo professor..
- k=5 r12 (nenhuma, correta=nao, fiel=False): A referência indica situações específicas de jubilamento, contradizendo a afirmação do assistente. Sem suporte: O regulamento não trata das situações em que o aluno é jubilado da UFG..
- k=5 r16 (total, correta=parcial, fiel=False): A resposta indica corretamente que a bolsa é obrigatória, mas atribui o pagamento à empresa, o que contradiz o regulamento que estabelece que o pagamento é feito pela instituição. Sem suporte: empresa deve pagar bolsa ao estagiário no estágio não obrigatório.
- k=5 r19 (total, correta=nao, fiel=False): A resposta omite a fórmula correta e apresenta informação errada, embora cite trechos corretos sobre precisão e reingresso. Sem suporte: O Índice de Prioridade (IP) é calculado a partir dos valores de TI, TA e IP; a fórmula apresentada (implícita) não corresponde ao IP = 100*TA + 10*TI - 3*QR.
