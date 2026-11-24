# Avaliação do agente (motor langgraph), conjunto teste

Gerado por scripts/avaliar_agente.py. Modelo do agente: openai/gpt-oss-20b, até 4 chamadas por pergunta. Juiz: openai/gpt-oss-120b. Ferramentas: buscar_regulamento (vetorial, artigo com seção, k=5) e consultar_calendario (híbrida com filtro de datas, até 8 eventos).

Perguntas avaliadas: 10 de 10.

## Por tipo de pergunta

| Métrica | Regulamento | Calendário | Mistas | Sem resposta |
|---|---|---|---|---|
| Perguntas | 7 | 0 | 0 | 3 |
| Correta (juiz: sim) | 2/7 (29%) | - | - | 2/3 (67%) |
| Correta ou parcial | 3/7 (43%) | - | - | 2/3 (67%) |
| Fiel às fontes citadas (juiz) | 3/5 (60%) | - | - | 0/1 (0%) |
| Ferramenta certa | 7/7 (100%) | - | - | - |
| Trecho anotado recuperado | 2/7 (29%) | - | - | - |
| Trecho anotado citado | 2/7 (29%) | - | - | - |
| Eventos anotados recuperados | - | - | - | - |
| Eventos anotados citados | - | - | - | - |
| "Não sei" (cobertura nenhuma) | 2/7 (29%) | - | - | 2/3 (67%) |
| Chamadas ao LLM (média) | 2.0 | - | - | 2.0 |

## Operação (todas as perguntas)

| Métrica | Valor |
|---|---|
| Respostas forçadas no último passo | 0 |
| Erros de ferramenta devolvidos ao modelo | 0 |
| Citações inválidas descartadas | 0 |
| Chamadas de ferramenta malformadas (repetidas) | 0 |
| Chamadas com sufixo do Harmony no nome (consertadas) | 1 |
| Latência p50 / p95 (ms) | 978 / 1544 |
| Tokens por pergunta (entrada / saída) | 2555 / 150 |
| Custo por 1.000 perguntas no plano pago (US$) | 0.24 |

Latência = chamadas ao LLM + ferramentas (embedding e SQL), sem as esperas do limite por minuto do plano grátis. Custo só do agente, sem o juiz.

## Respostas marcadas pelo juiz (correta = nao ou parcial, ou não fiel)

- t06 (sem_resposta, parcial, correta=nao, fiel=False): A referência indica que o tema não é tratado, mas o assistente afirma o contrário e usa um artigo irrelevante como suporte. Sem suporte: O regulamento não prevê que o professor possa pedir presença depois de 15 minutos de atraso. Ferramentas: buscar_regulamento({"consulta": "pode o professor pedir a presença dos alunos depois da aula, se passou 15 minutos"}).
- t01 (regulamento, nenhuma, correta=parcial, fiel=True): O assistente omite a informação da segunda chamada prevista nos arts. 83 e 84. Ferramentas: buscar_regulamento({"consulta": "o que acontece se ocorrer uma tragedia (tipo morte) durante uma prova de disciplina"}).
- t02 (regulamento, nenhuma, correta=nao, fiel=False): A referência indica que o regulamento permite aprovação com duas avaliações, contradizendo a afirmação do assistente. Sem suporte: O Regulamento Geral dos Cursos de Graduação e o Calendário Acadêmico da UFG não tratam de uma situação em que o estudante possa passar em uma matéria sem fazer prova.. Ferramentas: buscar_regulamento({"consulta": "posso passar de uma materia sem fazer prova?"}).
- t03 (regulamento, parcial, correta=nao, fiel=False): A resposta do assistente descreve procedimentos que não constam no RGCG para acompanhamento em provas, contradizendo a referência. Sem suporte: Para solicitar acompanhamento durante uma prova, o estudante deve pedir ao coordenador do curso, que verificará se atende aos requisitos e, se for o caso, solicitará a nomeação de uma banca examinadora.; A banca examinadora, que inclui o professor responsável, definirá os procedimentos de avaliação.. Ferramentas: buscar_regulamento({"consulta": "acompanhamento durante prova"}).
- t07 (regulamento, total, correta=nao, fiel=True): A resposta do assistente cita § 7º, que difere do § 6º indicado na referência, portanto está incorreta quanto à informação essencial. Ferramentas: buscar_regulamento({"consulta": "um professor pode passar outra prova sem ter divulgado o resultado da prova anterior?"}).
- t10 (regulamento, parcial, correta=nao, fiel=False): A resposta contradiz a referência que permite transferência e contém afirmação não respaldada por trechos citados. Sem suporte: Não é permitido cursar simultaneamente em mais de um curso de graduação na UFG (Art. 37).. Ferramentas: buscar_regulamento({"consulta": "posso comecar o curso em uma faculdade e terminar em outra?"}).
