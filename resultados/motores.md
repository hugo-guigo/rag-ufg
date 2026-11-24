# Motor manual x motor LangGraph (mesmas perguntas, mesmos dias)

Gerado por scripts/comparar_motores.py. Os dois motores usam as mesmas ferramentas, o mesmo prompt, o mesmo cliente HTTP e o mesmo modelo (openai/gpt-oss-20b); só muda o laço (docs/specs/langgraph.md). Latência = chamadas ao LLM + ferramentas, sem as esperas do limite por minuto do plano grátis. O modelo não é determinístico: parte da diferença em acertos pode ser variação entre execuções.

## 50 perguntas anotadas (50 em comum)

| Métrica | manual | langgraph |
|---|---|---|
| Correta (juiz: sim) | 42/50 (84%) | 43/50 (86%) |
| Correta ou parcial | 46/50 (92%) | 46/50 (92%) |
| Fiel às fontes citadas | 36/42 (86%) | 37/42 (88%) |
| Ferramenta certa | 42/42 (100%) | 42/42 (100%) |
| "Não sei" nas sem resposta | 6/8 (75%) | 6/8 (75%) |
| Chamadas ao LLM (média) | 2.18 | 2.18 |
| Respostas forçadas no último passo | 0 | 0 |
| Erros de ferramenta | 0 | 0 |
| Citações inválidas | 0 | 0 |
| Tokens por pergunta (entrada / saída) | 2806 / 151 | 2855 / 152 |
| Latência p50 / p95 (ms) | 951 / 1412 | 921 / 1602 |

Só o manual acertou: c04. Só o langgraph acertou: r17, r24.

## 10 perguntas em linguagem de aluno (10 em comum)

| Métrica | manual | langgraph |
|---|---|---|
| Correta (juiz: sim) | 3/10 (30%) | 4/10 (40%) |
| Correta ou parcial | 6/10 (60%) | 5/10 (50%) |
| Fiel às fontes citadas | 3/6 (50%) | 3/6 (50%) |
| Ferramenta certa | 7/7 (100%) | 7/7 (100%) |
| "Não sei" nas sem resposta | 2/3 (67%) | 2/3 (67%) |
| Chamadas ao LLM (média) | 2.10 | 2.00 |
| Respostas forçadas no último passo | 0 | 0 |
| Erros de ferramenta | 0 | 0 |
| Citações inválidas | 0 | 0 |
| Tokens por pergunta (entrada / saída) | 2956 / 165 | 2555 / 150 |
| Latência p50 / p95 (ms) | 909 / 1305 | 978 / 1544 |

Só o manual acertou: nenhuma. Só o langgraph acertou: t09.
