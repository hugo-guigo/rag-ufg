# Avaliação do agente (etapa 5), conjunto avaliacao

Gerado por scripts/avaliar_agente.py. Modelo do agente: openai/gpt-oss-20b, até 4 chamadas por pergunta. Juiz: openai/gpt-oss-120b. Ferramentas: buscar_regulamento (vetorial, artigo com seção, k=5) e consultar_calendario (híbrida com filtro de datas, até 8 eventos).

Perguntas avaliadas: 50 de 50.

## Por tipo de pergunta

| Métrica | Regulamento | Calendário | Mistas | Sem resposta |
|---|---|---|---|---|
| Perguntas | 32 | 8 | 2 | 8 |
| Correta (juiz: sim) | 25/32 (78%) | 7/8 (88%) | 1/2 (50%) | 8/8 (100%) |
| Correta ou parcial | 28/32 (88%) | 8/8 (100%) | 1/2 (50%) | 8/8 (100%) |
| Fiel às fontes citadas (juiz) | 25/30 (83%) | 7/8 (88%) | 1/2 (50%) | 1/2 (50%) |
| Ferramenta certa | 32/32 (100%) | 8/8 (100%) | 2/2 (100%) | - |
| Trecho anotado recuperado | 28/32 (88%) | - | 2/2 (100%) | - |
| Trecho anotado citado | 27/32 (84%) | - | 2/2 (100%) | - |
| Eventos anotados recuperados | - | 12/12 (100%) | 2/3 (67%) | - |
| Eventos anotados citados | - | 12/12 (100%) | 2/3 (67%) | - |
| "Não sei" (cobertura nenhuma) | 2/32 (6%) | 0/8 (0%) | 0/2 (0%) | 6/8 (75%) |
| Chamadas ao LLM (média) | 2.1 | 2.2 | 3.0 | 2.4 |

## Operação (todas as perguntas)

| Métrica | Valor |
|---|---|
| Respostas forçadas no último passo | 0 |
| Erros de ferramenta devolvidos ao modelo | 0 |
| Citações inválidas descartadas | 0 |
| Chamadas de ferramenta malformadas (repetidas) | 2 |
| Chamadas com sufixo do Harmony no nome (consertadas) | 3 |
| Latência p50 / p95 (ms) | 969 / 1919 |
| Tokens por pergunta (entrada / saída) | 2898 / 152 |
| Custo por 1.000 perguntas no plano pago (US$) | 0.26 |

Latência = chamadas ao LLM + ferramentas (embedding e SQL), sem as esperas do limite por minuto do plano grátis. Custo só do agente, sem o juiz.

## Agente vs RAG da etapa 4 (mesmas perguntas)

| Métrica | RAG etapa 4 (k=5) | Agente |
|---|---|---|
| Regulamento: correta (juiz: sim) | 23/32 (72%) | 25/32 (78%) |
| Regulamento: correta ou parcial | 29/32 (91%) | 28/32 (88%) |
| Regulamento: trecho anotado recuperado | 29/32 (91%) | 28/32 (88%) |
| Sem resposta: "não sei" | 8/8 (100%) | 6/8 (75%) |
| Tokens de entrada por pergunta | 1263 | 2811 |

No regulamento, o agente acertou e o RAG não: r14, r16, r17, r27. O RAG acertou e o agente não: r21, r24.
Calendário e mistas não entram na comparação: o RAG da etapa 4 só busca no regulamento.

## Respostas marcadas pelo juiz (correta = nao ou parcial, ou não fiel)

- c04 (calendario, total, correta=parcial, fiel=False): O assistente menciona apenas a data final, omitindo a data inicial, e atribui ao Art. 66 um detalhe que não consta no texto citado. Sem suporte: A afirmação de que o Art. 66 do RGCG indica o período de 27/07 a 27/08/2026 para cancelamento. Ferramentas: buscar_regulamento({"consulta": "até quando posso cancelar uma disciplina em 2026/2?"}), consultar_calendario({"data_fim": "2026-12-31", "data_inicio": "2026-01-01", "termo": "cancelamento de componente curricular 2026/2"}).
- m01 (misto, total, correta=nao, fiel=False): A resposta do assistente indica data diferente da referência e inclui informações não sustentadas pelos trechos fornecidos. Sem suporte: Até 27/08/2026 como prazo final para cancelamento; Afirmar que o prazo está conforme o calendário (E6) apesar de o calendário indicar período de 27/07 a 27/08; A menção de “até 30 dias antes do término das aulas” que não consta nos trechos citados. Ferramentas: buscar_regulamento({"consulta": "cancelar disciplina 2026/2 caso excepcional"}), consultar_calendario({"data_fim": "2026-12-31", "data_inicio": "2026-01-01", "termo": "cancelamento de disciplina 2026/2"}).
- s08 (sem_resposta, parcial, correta=sim, fiel=False): A resposta afirma que o regulamento não prevê a presença de animais, mas os trechos citados não tratam do assunto, portanto a afirmação não está sustentada pelas fontes. Sem suporte: O regulamento não prevê a presença de animais de estimação em sala de aula; Não há regra que permita ou proíba explicitamente levar um cachorro para a aula. Ferramentas: buscar_regulamento({"consulta": "Posso levar meu cachorro para a sala de aula?"}).
- r01 (regulamento, total, correta=parcial, fiel=True): O assistente menciona corretamente a nota mínima de 6,0, mas omite o requisito de frequência de 75% exigido pelo regulamento. Ferramentas: buscar_regulamento({"consulta": "nota mínima para passar numa disciplina"}).
- r09 (regulamento, nenhuma, correta=nao, fiel=False): A referência indica prazo de 5 dias após a consolidação, contradizendo a afirmação do assistente. Sem suporte: O regulamento geral dos cursos de graduação e o calendário acadêmico não tratam especificamente do prazo para contestar faltas lançadas pelo professor.. Ferramentas: buscar_regulamento({"consulta": "até quando posso contestar as faltas lançadas pelo professor?"}), consultar_calendario({"data_fim": "2026-12-31", "data_inicio": "2026-01-01", "termo": "contestação de faltas"}).
- r12 (regulamento, nenhuma, correta=nao, fiel=False): A resposta do assistente contradiz a referência ao afirmar que o regulamento não trata do tema, quando a referência indica artigos específicos. Sem suporte: O regulamento geral dos cursos de graduação e o calendário acadêmico não tratam de situações em que o aluno é jubilado da UFG.. Ferramentas: buscar_regulamento({"consulta": "Em que situações o aluno é jubilado da UFG?"}).
- r16 (regulamento, total, correta=sim, fiel=False): A resposta contém a informação correta, mas a referência ao artigo está errada, não sustentada pelos trechos citados. Sem suporte: cita o Art. 3º, § 3º em vez do Art. 22, § 3º. Ferramentas: buscar_regulamento({"consulta": "empresa tem que pagar bolsa estágio não obrigatório"}).
- r19 (regulamento, parcial, correta=parcial, fiel=False): A resposta omite a fórmula correta (IP = 100*TA + 10*TI - 3*QR) e inclui informações não presentes na referência, embora alguns trechos citados estejam corretos. Sem suporte: O Índice de Prioridade (IP) é calculado a partir dos valores de TI (tempo de inscrição), TA (tempo de atividade) e outros critérios de desempate, conforme Art. 53, Art. 55 e Art. 54 do RGCG.. Ferramentas: buscar_regulamento({"consulta": "Como é calculado o índice de prioridade da matrícula?"}).
- r21 (regulamento, parcial, correta=nao, fiel=False): A resposta contradiz a referência, que afirma ser possível cancelar até 30 dias antes do fim das aulas em caso excepcional. Sem suporte: Não, o prazo de cancelamento já passou.. Ferramentas: buscar_regulamento({"consulta": "cancelar disciplina"}), consultar_calendario({"data_fim": "2026-12-31", "data_inicio": "2026-01-01", "termo": "cancelamento de componentes curriculares"}).
- r24 (regulamento, parcial, correta=nao, fiel=False): A resposta omite e contradiz a regra do Art. 107 que garante aprovação com média 8,0, não sendo sustentada pelo trecho citado. Sem suporte: não há previsão de direito a aprovação automática por nota alta quando a reprovação se deu por falta.. Ferramentas: buscar_regulamento({"consulta": "reprovei por falta mas tirei nota 8"}).
- r25 (regulamento, total, correta=parcial, fiel=True): O assistente omite o requisito de 75% da carga horária exigido pela referência. Ferramentas: buscar_regulamento({"consulta": "aproveitar matérias que cursei em outra faculdade antes de entrar na UFG"}).
- r30 (regulamento, total, correta=sim, fiel=False): O conteúdo está correto, mas não há suporte nos trechos citados. Sem suporte: A afirmação de que a nota deve ser divulgada com antecedência de pelo menos 4 dias não está presente nos trechos citados (§ 7, § 8, § 9, § 10, § 11).; A referência ao Art. 82, § 6, não consta nos trechos fornecidos.. Ferramentas: buscar_regulamento({"consulta": "O professor pode aplicar a próxima prova sem ter divulgado a nota da anterior?"}).
