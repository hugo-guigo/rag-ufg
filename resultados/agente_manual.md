# Avaliação do agente (motor manual), conjunto avaliacao

Gerado por scripts/avaliar_agente.py. Modelo do agente: openai/gpt-oss-20b, até 4 chamadas por pergunta. Juiz: openai/gpt-oss-120b. Ferramentas: buscar_regulamento (vetorial, artigo com seção, k=5) e consultar_calendario (híbrida com filtro de datas, até 8 eventos).

Perguntas avaliadas: 50 de 50.

## Por tipo de pergunta

| Métrica | Regulamento | Calendário | Mistas | Sem resposta |
|---|---|---|---|---|
| Perguntas | 32 | 8 | 2 | 8 |
| Correta (juiz: sim) | 25/32 (78%) | 8/8 (100%) | 1/2 (50%) | 8/8 (100%) |
| Correta ou parcial | 29/32 (91%) | 8/8 (100%) | 1/2 (50%) | 8/8 (100%) |
| Fiel às fontes citadas (juiz) | 27/30 (90%) | 8/8 (100%) | 0/2 (0%) | 1/2 (50%) |
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
| Chamadas de ferramenta malformadas (repetidas) | 0 |
| Chamadas com sufixo do Harmony no nome (consertadas) | 6 |
| Latência p50 / p95 (ms) | 951 / 1412 |
| Tokens por pergunta (entrada / saída) | 2806 / 151 |
| Custo por 1.000 perguntas no plano pago (US$) | 0.26 |

Latência = chamadas ao LLM + ferramentas (embedding e SQL), sem as esperas do limite por minuto do plano grátis. Custo só do agente, sem o juiz.

## Agente vs RAG da etapa 4 (mesmas perguntas)

| Métrica | RAG etapa 4 (k=5) | Agente |
|---|---|---|
| Regulamento: correta (juiz: sim) | 23/32 (72%) | 25/32 (78%) |
| Regulamento: correta ou parcial | 29/32 (91%) | 29/32 (91%) |
| Regulamento: trecho anotado recuperado | 29/32 (91%) | 28/32 (88%) |
| Sem resposta: "não sei" | 8/8 (100%) | 6/8 (75%) |
| Tokens de entrada por pergunta | 1263 | 2796 |

No regulamento, o agente acertou e o RAG não: r01, r14, r16, r27. O RAG acertou e o agente não: r04, r24.
Calendário e mistas não entram na comparação: o RAG da etapa 4 só busca no regulamento.

## Respostas marcadas pelo juiz (correta = nao ou parcial, ou não fiel)

- m01 (misto, total, correta=nao, fiel=False): A data informada pelo assistente diverge da resposta de referência, que indica 13 de novembro de 2026. Sem suporte: até 27/08/2026. Ferramentas: buscar_regulamento({"consulta": "cancelar disciplina 2026/2 caso excepcional"}), consultar_calendario({"data_fim": "2026-12-31", "data_inicio": "2026-01-01", "termo": "cancelamento de disciplina 2026/2"}).
- m02 (misto, total, correta=sim, fiel=False): Inclui a informação essencial correta, mas contém afirmação não suportada pelos trechos citados. Sem suporte: Cada trancamento tem validade de um semestre (Art. 72).. Ferramentas: buscar_regulamento({"consulta": "quantas vezes posso trancar o curso"}), consultar_calendario({"termo": "trancamento de matrícula 2027/1", "data_inicio": "2027-01-01", "data_fim": "2027-12-31"}).
- s08 (sem_resposta, parcial, correta=sim, fiel=False): A resposta afirma que o regulamento trata ou não trata de animais, mas os trechos citados não contêm nenhuma referência a esse assunto. Sem suporte: O regulamento não prevê a presença de animais de estimação em sala de aula.; Não há regra que permita ou proíba explicitamente levar um cachorro para a aula.; Se houver necessidade, seria necessário solicitar autorização ao professor e à coordenação. Ferramentas: buscar_regulamento({"consulta": "Posso levar meu cachorro para a sala de aula?"}).
- r04 (regulamento, total, correta=parcial, fiel=True): Acrescentou condição do Art. 77 que não está na referência, mas está correta e suportada. Ferramentas: buscar_regulamento({"consulta": "trancar a matrícula logo no meu primeiro semestre"}).
- r09 (regulamento, nenhuma, correta=nao, fiel=False): A resposta contradiz a referência, que indica prazo de 5 dias após a consolidação da turma (Art. 89). Sem suporte: O Regulamento Geral dos Cursos de Graduação e o Calendário Acadêmico 2026 não tratam especificamente do prazo para contestar faltas lançadas pelo professor.. Ferramentas: buscar_regulamento({"consulta": "até quando posso contestar as faltas lançadas pelo professor?"}), consultar_calendario({"data_fim": "2026-12-31", "data_inicio": "2026-01-01", "termo": "contestação de faltas"}).
- r12 (regulamento, nenhuma, correta=nao, fiel=False): A resposta contradiz a referência, que indica situações específicas de jubilamento. Sem suporte: O regulamento geral dos cursos de graduação e o calendário acadêmico da UFG não tratam de situações em que o aluno é jubilado.. Ferramentas: buscar_regulamento({"consulta": "Em que situações o aluno é jubilado da UFG?"}).
- r16 (regulamento, total, correta=sim, fiel=False): Conteúdo essencial está correto, mas a referência ao número do artigo está incorreta e não é sustentada pelas fontes. Sem suporte: Citação do artigo como "Art. 3º, § 3º" em vez de "Art. 22, § 3º". Ferramentas: buscar_regulamento({"consulta": "empresa tem que pagar bolsa estágio não obrigatório"}).
- r17 (regulamento, total, correta=parcial, fiel=True): O assistente indica a frequência de 100% correta, mas omite a informação de reposição para faltas justificadas presente na referência. Ferramentas: buscar_regulamento({"consulta": "frequência exigida no estágio obrigatório"}).
- r19 (regulamento, total, correta=parcial, fiel=True): Fornece critérios de desempate e precisão, mas omite a fórmula de cálculo do IP presente na referência. Ferramentas: buscar_regulamento({"consulta": "Como é calculado o índice de prioridade da matrícula?"}).
- r24 (regulamento, parcial, correta=nao, fiel=False): A resposta contradiz a referência que garante aprovação com média 8,0 ou mais e não tem suporte no artigo citado. Sem suporte: não há previsão de direito a aprovação por nota alta quando a reprovação foi por falta. Ferramentas: buscar_regulamento({"consulta": "reprovei por falta mas tirei nota 8"}).
- r25 (regulamento, total, correta=parcial, fiel=True): O assistente omite a exigência de 75% da carga horária e equivalência de conteúdo citada na referência. Ferramentas: buscar_regulamento({"consulta": "aproveitar matérias que cursei em outra faculdade antes de entrar na UFG"}).
- r30 (regulamento, total, correta=sim, fiel=False): A afirmação de 4 dias não está presente nos trechos citados pelo assistente. Sem suporte: antecedência de pelo menos 4 (quatro) dias; Art. 82, § 6. Ferramentas: buscar_regulamento({"consulta": "O professor pode aplicar a próxima prova sem ter divulgado a nota da anterior?"}).
