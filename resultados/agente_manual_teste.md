# Avaliação do agente (motor manual), conjunto teste

Gerado por scripts/avaliar_agente.py. Modelo do agente: openai/gpt-oss-20b, até 4 chamadas por pergunta. Juiz: openai/gpt-oss-120b. Ferramentas: buscar_regulamento (vetorial, artigo com seção, k=5) e consultar_calendario (híbrida com filtro de datas, até 8 eventos).

Perguntas avaliadas: 10 de 10.

## Por tipo de pergunta

| Métrica | Regulamento | Calendário | Mistas | Sem resposta |
|---|---|---|---|---|
| Perguntas | 7 | 0 | 0 | 3 |
| Correta (juiz: sim) | 1/7 (14%) | - | - | 2/3 (67%) |
| Correta ou parcial | 4/7 (57%) | - | - | 2/3 (67%) |
| Fiel às fontes citadas (juiz) | 3/5 (60%) | - | - | 0/1 (0%) |
| Ferramenta certa | 7/7 (100%) | - | - | - |
| Trecho anotado recuperado | 2/7 (29%) | - | - | - |
| Trecho anotado citado | 2/7 (29%) | - | - | - |
| Eventos anotados recuperados | - | - | - | - |
| Eventos anotados citados | - | - | - | - |
| "Não sei" (cobertura nenhuma) | 2/7 (29%) | - | - | 2/3 (67%) |
| Chamadas ao LLM (média) | 2.0 | - | - | 2.3 |

## Operação (todas as perguntas)

| Métrica | Valor |
|---|---|
| Respostas forçadas no último passo | 0 |
| Erros de ferramenta devolvidos ao modelo | 0 |
| Citações inválidas descartadas | 0 |
| Chamadas de ferramenta malformadas (repetidas) | 0 |
| Chamadas com sufixo do Harmony no nome (consertadas) | 0 |
| Latência p50 / p95 (ms) | 909 / 1305 |
| Tokens por pergunta (entrada / saída) | 2956 / 165 |
| Custo por 1.000 perguntas no plano pago (US$) | 0.27 |

Latência = chamadas ao LLM + ferramentas (embedding e SQL), sem as esperas do limite por minuto do plano grátis. Custo só do agente, sem o juiz.

## Respostas marcadas pelo juiz (correta = nao ou parcial, ou não fiel)

- t06 (sem_resposta, parcial, correta=nao, fiel=False): A referência indica que o assunto não é tratado, mas o assistente afirma que o regulamento impede e cita artigo irrelevante. Sem suporte: O regulamento não prevê que o professor possa pedir presença depois de 15 minutos de atraso. Ferramentas: buscar_regulamento({"consulta": "pode o professor pedir a presença dos alunos depois da aula, se passou 15 minutos"}).
- t01 (regulamento, nenhuma, correta=parcial, fiel=True): O assistente omite a informação da segunda chamada presente na referência. Ferramentas: buscar_regulamento({"consulta": "o que acontece se ocorrer uma tragedia (tipo morte) durante uma prova de disciplina"}).
- t02 (regulamento, nenhuma, correta=nao, fiel=False): A resposta do assistente contradiz a referência ao afirmar que o regulamento não trata, quando a referência indica que há regra específica. Sem suporte: O Regulamento Geral dos Cursos de Graduação e o Calendário Acadêmico da UFG não tratam de uma situação em que o estudante possa passar em uma matéria sem fazer prova.. Ferramentas: buscar_regulamento({"consulta": "posso passar de uma materia sem fazer prova?"}).
- t03 (regulamento, parcial, correta=parcial, fiel=False): A resposta omite a exceção prevista no Art. 117 e inclui procedimentos não sustentados pelos trechos citados. Sem suporte: Para solicitar acompanhamento durante uma prova, o estudante deve pedir ao coordenador do curso, que verificará se atende aos requisitos e, se for o caso, solicitará a nomeação de uma banca examinadora.; O regulamento não prevê um procedimento específico para acompanhamento, apenas a composição da banca e os critérios de avaliação.. Ferramentas: buscar_regulamento({"consulta": "acompanhamento durante prova"}).
- t07 (regulamento, total, correta=nao, fiel=True): A resposta do assistente não corresponde à informação essencial da referência (Art. 82, §6º) embora esteja suportada pelo §7 citado. Ferramentas: buscar_regulamento({"consulta": "um professor pode passar outra prova sem ter divulgado o resultado da prova anterior?"}).
- t09 (regulamento, total, correta=parcial, fiel=True): Fornece todas as formas do Art. 32 corretamente, mas inclui informações adicionais do Art. 31 que não estavam na referência. Ferramentas: buscar_regulamento({"consulta": "formas de ingresso na ufg"}).
- t10 (regulamento, parcial, correta=nao, fiel=False): A resposta contradiz a referência que afirma ser possível mediante transferência e não está sustentada pelos trechos citados. Sem suporte: Não é permitido iniciar um curso na UFG e concluí‑lo em outra instituição.; O RGCG Art. 93 permite apenas a transferência de até dois componentes curriculares para outra IES reconhecida, mas o estudante deve permanecer vinculado a uma única matriz curricular na UFG.. Ferramentas: buscar_regulamento({"consulta": "posso comecar o curso em uma faculdade e terminar em outra?"}).
