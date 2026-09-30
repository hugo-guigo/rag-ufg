# Avaliação do agente (etapa 5), conjunto teste

Gerado por scripts/avaliar_agente.py. Modelo do agente: openai/gpt-oss-20b, até 4 chamadas por pergunta. Juiz: openai/gpt-oss-120b. Ferramentas: buscar_regulamento (vetorial, artigo com seção, k=5) e consultar_calendario (híbrida com filtro de datas, até 8 eventos).

Perguntas avaliadas: 10 de 50.

## Por tipo de pergunta

| Métrica | Regulamento | Calendário | Mistas | Sem resposta |
|---|---|---|---|---|
| Perguntas | 7 | 0 | 0 | 3 |
| Correta (juiz: sim) | 1/7 (14%) | - | - | 1/3 (33%) |
| Correta ou parcial | 4/7 (57%) | - | - | 2/3 (67%) |
| Fiel às fontes citadas (juiz) | 3/6 (50%) | - | - | 0/2 (0%) |
| Ferramenta certa | 7/7 (100%) | - | - | - |
| Trecho anotado recuperado | 2/7 (29%) | - | - | - |
| Trecho anotado citado | 2/7 (29%) | - | - | - |
| Eventos anotados recuperados | - | - | - | - |
| Eventos anotados citados | - | - | - | - |
| "Não sei" (cobertura nenhuma) | 1/7 (14%) | - | - | 1/3 (33%) |
| Chamadas ao LLM (média) | 2.0 | - | - | 2.0 |

## Operação (todas as perguntas)

| Métrica | Valor |
|---|---|
| Respostas forçadas no último passo | 0 |
| Erros de ferramenta devolvidos ao modelo | 0 |
| Citações inválidas descartadas | 0 |
| Chamadas de ferramenta malformadas (repetidas) | 0 |
| Chamadas com sufixo do Harmony no nome (consertadas) | 2 |
| Latência p50 / p95 (ms) | 1055 / 1296 |
| Tokens por pergunta (entrada / saída) | 2354 / 143 |
| Custo por 1.000 perguntas no plano pago (US$) | 0.22 |

Latência = chamadas ao LLM + ferramentas (embedding e SQL), sem as esperas do limite por minuto do plano grátis. Custo só do agente, sem o juiz.

## Respostas marcadas pelo juiz (correta = nao ou parcial, ou não fiel)

- t04 (sem_resposta, parcial, correta=parcial, fiel=False): A resposta indica que o regulamento não prevê sanções por greve, mas acrescenta informação não sustentada sobre regime disciplinar que não consta nas fontes citadas. Sem suporte: o estudante pode estar sujeito ao regime disciplinar conforme resolução específica da UFG. Ferramentas: buscar_regulamento({"consulta": "sou penalizado por participar de uma greve?"}).
- t06 (sem_resposta, parcial, correta=nao, fiel=False): A resposta do assistente afirma que o regulamento proíbe a exigência de presença após a aula, mas o trecho citado trata de acréscimo de componentes curriculares e não sustenta essa afirmação. Sem suporte: O regulamento não prevê que o professor possa exigir presença após o término da aula.; Ele só pode solicitar presença dentro do horário oficial de aula.. Ferramentas: buscar_regulamento({"consulta": "ele pode pedir a presença dos alunos?"}).
- t01 (regulamento, nenhuma, correta=parcial, fiel=True): O assistente omite a informação da segunda chamada presente na referência. Ferramentas: buscar_regulamento({"consulta": "o que acontece se ocorrer uma tragedia (tipo morte) durante uma prova de disciplina"}).
- t02 (regulamento, parcial, correta=nao, fiel=False): A resposta contradiz a referência e usa artigo irrelevante que não sustenta a afirmação. Sem suporte: Não é possível passar de uma matéria sem fazer prova.; O RGCG Art. 40 estabelece que a aprovação em componente curricular isolado não assegura direito a diploma, apenas certificado.. Ferramentas: buscar_regulamento({"consulta": "passar de uma materia sem fazer prova"}).
- t03 (regulamento, parcial, correta=nao, fiel=False): A resposta do assistente introduz procedimentos que não constam no RGCG e não são sustentados pelos trechos citados. Sem suporte: O estudante deve pedir ao coordenador do curso, que verificará se atende aos requisitos e, se for o caso, solicitará a nomeação de uma banca examinadora.; A banca examinadora, que inclui o professor responsável, definirá os procedimentos de avaliação.; O regulamento não detalha um procedimento específico de acompanhamento, apenas estabelece que o pedido será analisado pelo coordenador e que a banca definirá a sistemática de avaliação.. Ferramentas: buscar_regulamento({"consulta": "acompanhamento durante prova"}).
- t07 (regulamento, total, correta=parcial, fiel=True): A resposta indica corretamente que a prova não pode ser aplicada sem divulgação prévia, mas cita o § 7 em vez do § 6 que fixa o prazo de 4 dias. Ferramentas: buscar_regulamento({"consulta": "um professor pode passar outra prova sem ter divulgado o resultado da prova anterior?"}).
- t09 (regulamento, total, correta=parcial, fiel=True): Inclui informações corretas do Art. 32, mas acrescenta itens adicionais que não constam da referência, embora estejam suportados por Art. 31. Ferramentas: buscar_regulamento({"consulta": "formas de ingresso na ufg"}).
- t10 (regulamento, parcial, correta=nao, fiel=False): A resposta contradiz a referência que afirma ser possível por transferência e não está sustentada pelos trechos citados. Sem suporte: Não é permitido iniciar um curso na UFG e concluí‑lo em outra instituição.; O RGCG Art. 93 permite apenas a transferência de até dois componentes curriculares para outra IES reconhecida, mas o estudante deve permanecer vinculado a uma única matriz curricular na UFG.. Ferramentas: buscar_regulamento({"consulta": "posso comecar o curso em uma faculdade e terminar em outra?"}).
