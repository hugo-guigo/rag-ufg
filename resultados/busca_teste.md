# Avaliação da busca (sem LLM), conjunto teste

7 perguntas com resposta no regulamento e 3 sem resposta.
Acerto = o trecho devolvido contém a frase anotada com a resposta. Gerado por scripts/avaliar_busca.py.

| Modelo | Estratégia | Busca | Trechos | Caracteres (média) | Artigos por trecho | R@1 | R@3 | R@5 | R@10 | MRR@10 | R@5 (critério artigo) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| multilingual-e5-small-int8 | artigo_secao | vetor | 142 | 611 | 1.0 | 29% | 43% | 43% | 57% | 0.38 | 57% |

## Comparações pareadas (acerto no top 5)

| Comparação (A vs B) | Só A acerta | Só B acerta |
|---|---|---|

## A similaridade do 1º resultado separa "tem resposta" de "não sei"?

| Modelo | Estratégia | Busca | Com resposta (mín / mediana / máx) | Sem resposta (mín / mediana / máx) | Melhor limiar | Acurácia com ele |
|---|---|---|---|---|---|---|
| multilingual-e5-small-int8 | artigo_secao | vetor | 0.845 / 0.856 / 0.908 | 0.844 / 0.863 / 0.878 | 0.845 | 80% |

O limiar foi escolhido olhando as próprias perguntas, então a acurácia dele é otimista.

## Latência (ms, CPU local)

| Modelo | Estratégia | Busca | Embedding da pergunta p50 / p95 | Busca no banco p50 / p95 |
|---|---|---|---|---|
| multilingual-e5-small-int8 | artigo_secao | vetor | 5 / 7 | 2.9 / 20.0 |

## Perguntas sem acerto no top 5

- multilingual-e5-small-int8 / artigo_secao / vetor: t01, t02, t07, t10
