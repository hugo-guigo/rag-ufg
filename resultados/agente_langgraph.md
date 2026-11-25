# Avaliação do agente (motor langgraph), conjunto avaliacao

Gerado por scripts/avaliar_agente.py. Modelo do agente: openai/gpt-oss-20b, até 4 chamadas por pergunta. Juiz: openai/gpt-oss-120b. Ferramentas: buscar_regulamento (vetorial, artigo com seção, k=5) e consultar_calendario (híbrida com filtro de datas, até 8 eventos).

Perguntas avaliadas: 50 de 50.

## Por tipo de pergunta

| Métrica | Regulamento | Calendário | Mistas | Sem resposta |
|---|---|---|---|---|
| Perguntas | 32 | 8 | 2 | 8 |
| Correta (juiz: sim) | 27/32 (84%) | 7/8 (88%) | 1/2 (50%) | 8/8 (100%) |
| Correta ou parcial | 30/32 (94%) | 7/8 (88%) | 1/2 (50%) | 8/8 (100%) |
| Fiel às fontes citadas (juiz) | 27/30 (90%) | 7/8 (88%) | 2/2 (100%) | 1/2 (50%) |
| Ferramenta certa | 32/32 (100%) | 8/8 (100%) | 2/2 (100%) | - |
| Trecho anotado recuperado | 29/32 (91%) | - | 2/2 (100%) | - |
| Trecho anotado citado | 27/32 (84%) | - | 2/2 (100%) | - |
| Eventos anotados recuperados | - | 11/12 (92%) | 2/3 (67%) | - |
| Eventos anotados citados | - | 11/12 (92%) | 2/3 (67%) | - |
| "Não sei" (cobertura nenhuma) | 2/32 (6%) | 0/8 (0%) | 0/2 (0%) | 6/8 (75%) |
| Chamadas ao LLM (média) | 2.1 | 2.2 | 3.0 | 2.4 |

## Operação (todas as perguntas)

| Métrica | Valor |
|---|---|
| Respostas forçadas no último passo | 0 |
| Erros de ferramenta devolvidos ao modelo | 0 |
| Citações inválidas descartadas | 0 |
| Chamadas de ferramenta malformadas (repetidas) | 0 |
| Chamadas com sufixo do Harmony no nome (consertadas) | 5 |
| Latência p50 / p95 (ms) | 921 / 1602 |
| Tokens por pergunta (entrada / saída) | 2855 / 152 |
| Custo por 1.000 perguntas no plano pago (US$) | 0.26 |

Latência = chamadas ao LLM + ferramentas (embedding e SQL), sem as esperas do limite por minuto do plano grátis. Custo só do agente, sem o juiz.

## Agente vs RAG da etapa 4 (mesmas perguntas)

| Métrica | RAG etapa 4 (k=5) | Agente |
|---|---|---|
| Regulamento: correta (juiz: sim) | 23/32 (72%) | 27/32 (84%) |
| Regulamento: correta ou parcial | 29/32 (91%) | 30/32 (94%) |
| Regulamento: trecho anotado recuperado | 29/32 (91%) | 29/32 (91%) |
| Sem resposta: "não sei" | 8/8 (100%) | 6/8 (75%) |
| Tokens de entrada por pergunta | 1263 | 2856 |

No regulamento, o agente acertou e o RAG não: r01, r14, r16, r17, r27. O RAG acertou e o agente não: r04.
Calendário e mistas não entram na comparação: o RAG da etapa 4 só busca no regulamento.

## Respostas marcadas pelo juiz (correta = nao ou parcial, ou não fiel)

- c04 (calendario, parcial, correta=nao, fiel=False): A resposta não fornece o período correto (27/07 a 27/08/2026) e inclui afirmações não sustentadas. Sem suporte: não há registro de período específico para 2026/2, então verifique o calendário oficial para a data exata. Ferramentas: buscar_regulamento({"consulta": "até quando posso cancelar uma disciplina em 2026/2"}), consultar_calendario({"data_fim": "2026-06-30", "data_inicio": "2026-02-01", "termo": "cancelamento de componente curricular 2026/2"}).
- m01 (misto, total, correta=nao, fiel=True): A resposta indica 27/08/2026 como prazo, divergindo da referência que fixa 13/11/2026, embora as demais informações estejam corretas e sustentadas. Ferramentas: buscar_regulamento({"consulta": "cancelar disciplina 2026/2 caso excepcional"}), consultar_calendario({"data_fim": "2026-12-31", "data_inicio": "2026-01-01", "termo": "cancelamento de disciplina 2026/2"}).
- s06 (sem_resposta, nenhuma, correta=sim, fiel=False): A resposta afirma que o regulamento e o calendário não tratam do prazo, mas não apresenta nenhum trecho como suporte. Sem suporte: O Regulamento Geral dos Cursos de Graduação e o Calendário Acadêmico 2026 não tratam especificamente do prazo para entrega do TCC no curso de Ciência da Computação.. Ferramentas: buscar_regulamento({"consulta": "prazo para entregar o TCC no curso de Ciência da Computação"}), consultar_calendario({"data_fim": "2026-12-31", "data_inicio": "2026-01-01", "termo": "prazo entrega TCC"}).
- s08 (sem_resposta, parcial, correta=sim, fiel=False): A resposta afirma que o regulamento não trata do assunto, mas não há suporte nos trechos citados. Sem suporte: O regulamento não prevê a presença de animais de estimação em sala de aula.; Não há regra que permita ou proíba explicitamente levar um cachorro para a aula.; Se houver necessidade, seria necessário solicitar autorização ao professor e à coordenação. Ferramentas: buscar_regulamento({"consulta": "Posso levar meu cachorro para a sala de aula?"}).
- r04 (regulamento, total, correta=parcial, fiel=True): Acrescentou condição do Art. 77 que não está na referência, mas está correta e suportada. Ferramentas: buscar_regulamento({"consulta": "trancar a matrícula logo no meu primeiro semestre"}).
- r09 (regulamento, nenhuma, correta=nao, fiel=False): A referência indica prazo de 5 dias após a consolidação (Art. 89), contradizendo a afirmação do assistente. Sem suporte: O Regulamento Geral dos Cursos de Graduação e o Calendário Acadêmico 2026 não tratam especificamente do prazo para contestar faltas lançadas pelo professor.. Ferramentas: buscar_regulamento({"consulta": "até quando posso contestar as faltas lançadas pelo professor?"}), consultar_calendario({"data_fim": "2026-12-31", "data_inicio": "2026-01-01", "termo": "contestação de faltas"}).
- r10 (regulamento, total, correta=sim, fiel=False): A informação está correta, mas não há suporte nos trechos citados, que tratam do Art. 91, não do Art. 12. Sem suporte: A carga horária total do Núcleo Livre (NL) em cada curso presencial deve ser de, no mínimo, 128 (cento e vinte e oito) horas. (Art. 12, § 4). Ferramentas: buscar_regulamento({"consulta": "Quantas horas de núcleo livre preciso cursar?"}).
- r12 (regulamento, nenhuma, correta=nao, fiel=False): A resposta contradiz a referência, que indica artigos específicos sobre jubilamento. Sem suporte: O regulamento geral dos cursos de graduação e o calendário acadêmico não tratam de situações em que o aluno é jubilado da UFG.. Ferramentas: buscar_regulamento({"consulta": "Em que situações o aluno é jubilado da UFG?"}).
- r16 (regulamento, total, correta=sim, fiel=False): A resposta contém a informação correta, mas o número do artigo citado não está sustentado pelas fontes. Sem suporte: Cita o Art. 3º, § 3º em vez do Art. 22, § 3º. Ferramentas: buscar_regulamento({"consulta": "empresa tem que pagar bolsa estágio não obrigatório"}).
- r19 (regulamento, total, correta=parcial, fiel=True): Fornece critérios de desempate e precisão, mas omite a fórmula exata do IP presente na referência. Ferramentas: buscar_regulamento({"consulta": "Como é calculado o índice de prioridade da matrícula?"}).
- r25 (regulamento, total, correta=parcial, fiel=True): O assistente omite a exigência de 75% da carga horária e equivalência de conteúdo exigida pela referência. Ferramentas: buscar_regulamento({"consulta": "aproveitar matérias que cursei em outra faculdade antes de entrar na UFG"}).
- r30 (regulamento, total, correta=sim, fiel=False): A resposta contém a informação essencial, mas o trecho citado não comprova o prazo de 4 dias mencionado. Sem suporte: antecedência de pelo menos 4 (quatro) dias; Art. 82, § 6. Ferramentas: buscar_regulamento({"consulta": "O professor pode aplicar a próxima prova sem ter divulgado a nota da anterior?"}).
