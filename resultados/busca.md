# Avaliação da busca (sem LLM)

34 perguntas com resposta no regulamento (32 do regulamento e 2 mistas) e 8 sem resposta.
Acerto = o trecho devolvido contém a frase anotada com a resposta. Gerado por scripts/avaliar_busca.py.

| Modelo | Estratégia | Busca | Trechos | Caracteres (média) | Artigos por trecho | R@1 | R@3 | R@5 | R@10 | MRR@10 | R@5 (critério artigo) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| multilingual-e5-small-int8 | artigo | vetor | 142 | 611 | 1.0 | 44% | 65% | 71% | 76% | 0.56 | 74% |
| multilingual-e5-small-int8 | artigo_secao | vetor | 142 | 611 | 1.0 | 59% | 79% | 88% | 94% | 0.70 | 91% |
| multilingual-e5-small-int8 | artigo_sem_contexto | vetor | 142 | 611 | 1.0 | 56% | 85% | 85% | 94% | 0.71 | 88% |
| multilingual-e5-small-int8 | janela800 | vetor | 134 | 793 | 2.1 | 35% | 62% | 68% | 82% | 0.51 | 88% |
| multilingual-e5-small-int8 | janela400 | vetor | 271 | 395 | 1.6 | 38% | 65% | 71% | 82% | 0.51 | 88% |
| multilingual-e5-small-int8 | artigo | texto | 142 | 611 | 1.0 | 44% | 62% | 71% | 88% | 0.56 | 74% |
| multilingual-e5-small-int8 | artigo_secao | texto | 142 | 611 | 1.0 | 44% | 62% | 71% | 88% | 0.56 | 74% |
| multilingual-e5-small-int8 | artigo_sem_contexto | texto | 142 | 611 | 1.0 | 44% | 62% | 71% | 88% | 0.56 | 74% |
| multilingual-e5-small-int8 | janela800 | texto | 134 | 793 | 2.1 | 38% | 65% | 76% | 88% | 0.54 | 85% |
| multilingual-e5-small-int8 | janela400 | texto | 271 | 395 | 1.6 | 32% | 50% | 56% | 71% | 0.44 | 71% |
| multilingual-e5-small-int8 | artigo | hibrida | 142 | 611 | 1.0 | 59% | 74% | 76% | 91% | 0.68 | 82% |
| multilingual-e5-small-int8 | artigo_secao | hibrida | 142 | 611 | 1.0 | 62% | 74% | 79% | 91% | 0.71 | 82% |
| multilingual-e5-small-int8 | artigo_sem_contexto | hibrida | 142 | 611 | 1.0 | 65% | 79% | 82% | 94% | 0.73 | 85% |
| multilingual-e5-small-int8 | janela800 | hibrida | 134 | 793 | 2.1 | 47% | 79% | 79% | 94% | 0.63 | 91% |
| multilingual-e5-small-int8 | janela400 | hibrida | 271 | 395 | 1.6 | 41% | 74% | 76% | 79% | 0.57 | 88% |
| multilingual-e5-small-fp32 | artigo | vetor | 142 | 611 | 1.0 | 44% | 68% | 74% | 82% | 0.57 | 76% |
| multilingual-e5-small-fp32 | artigo_secao | vetor | 142 | 611 | 1.0 | 56% | 79% | 85% | 94% | 0.69 | 91% |
| multilingual-e5-small-fp32 | artigo_sem_contexto | vetor | 142 | 611 | 1.0 | 53% | 76% | 88% | 91% | 0.67 | 91% |
| multilingual-e5-small-fp32 | janela800 | vetor | 134 | 793 | 2.1 | 38% | 62% | 68% | 88% | 0.53 | 91% |
| multilingual-e5-small-fp32 | janela400 | vetor | 271 | 395 | 1.6 | 38% | 59% | 65% | 79% | 0.51 | 82% |

## Comparações pareadas (acerto no top 5)

| Comparação (A vs B) | Só A acerta | Só B acerta |
|---|---|---|
| contexto completo vs só a seção | 0 (-) | 6 (r01, r02, r03, r15, r26, r30) |
| só a seção vs sem contexto | 2 (r04, r23) | 1 (m02) |
| por artigo vs janela de 800 | 9 (r02, r10, r13, r15, r17, r18, r23, r25, r30) | 2 (r19, m02) |
| janela de 800 vs janela de 400 | 4 (r01, r04, r11, r14) | 5 (r17, r18, r23, r25, r30) |
| vetorial vs híbrida | 3 (r03, r04, r27) | 0 (-) |
| int8 vs fp32 | 1 (r27) | 0 (-) |

## A similaridade do 1º resultado separa "tem resposta" de "não sei"?

| Modelo | Estratégia | Busca | Com resposta (mín / mediana / máx) | Sem resposta (mín / mediana / máx) | Melhor limiar | Acurácia com ele |
|---|---|---|---|---|---|---|
| multilingual-e5-small-int8 | artigo | vetor | 0.845 / 0.881 / 0.899 | 0.834 / 0.851 / 0.898 | 0.845 | 88% |
| multilingual-e5-small-int8 | artigo_secao | vetor | 0.845 / 0.884 / 0.912 | 0.840 / 0.850 / 0.902 | 0.845 | 90% |
| multilingual-e5-small-int8 | artigo_sem_contexto | vetor | 0.835 / 0.886 / 0.912 | 0.832 / 0.849 / 0.898 | 0.850 | 90% |
| multilingual-e5-small-int8 | janela800 | vetor | 0.835 / 0.877 / 0.901 | 0.829 / 0.854 / 0.896 | 0.856 | 88% |
| multilingual-e5-small-int8 | janela400 | vetor | 0.837 / 0.880 / 0.898 | 0.836 / 0.846 / 0.886 | 0.848 | 90% |
| multilingual-e5-small-int8 | artigo | texto | 0.819 / 0.865 / 0.897 | 0.831 / 0.836 / 0.855 | 0.835 | 86% |
| multilingual-e5-small-int8 | artigo_secao | texto | 0.828 / 0.872 / 0.906 | 0.818 / 0.839 / 0.858 | 0.842 | 90% |
| multilingual-e5-small-int8 | artigo_sem_contexto | texto | 0.826 / 0.865 / 0.912 | 0.803 / 0.835 / 0.858 | 0.840 | 88% |
| multilingual-e5-small-int8 | janela800 | texto | 0.822 / 0.867 / 0.892 | 0.809 / 0.834 / 0.894 | 0.835 | 88% |
| multilingual-e5-small-int8 | janela400 | texto | 0.824 / 0.870 / 0.898 | 0.808 / 0.836 / 0.871 | 0.831 | 88% |
| multilingual-e5-small-int8 | artigo | hibrida | 0.842 / 0.877 / 0.897 | 0.831 / 0.842 / 0.898 | 0.842 | 90% |
| multilingual-e5-small-int8 | artigo_secao | hibrida | 0.842 / 0.884 / 0.906 | 0.832 / 0.842 / 0.902 | 0.842 | 90% |
| multilingual-e5-small-int8 | artigo_sem_contexto | hibrida | 0.826 / 0.886 / 0.912 | 0.831 / 0.846 / 0.898 | 0.848 | 88% |
| multilingual-e5-small-int8 | janela800 | hibrida | 0.835 / 0.871 / 0.898 | 0.823 / 0.845 / 0.894 | 0.835 | 88% |
| multilingual-e5-small-int8 | janela400 | hibrida | 0.837 / 0.874 / 0.898 | 0.826 / 0.839 / 0.886 | 0.858 | 93% |
| multilingual-e5-small-fp32 | artigo | vetor | 0.843 / 0.880 / 0.901 | 0.834 / 0.847 / 0.896 | 0.843 | 88% |
| multilingual-e5-small-fp32 | artigo_secao | vetor | 0.851 / 0.884 / 0.911 | 0.836 / 0.846 / 0.899 | 0.851 | 93% |
| multilingual-e5-small-fp32 | artigo_sem_contexto | vetor | 0.839 / 0.884 / 0.901 | 0.832 / 0.848 / 0.897 | 0.850 | 90% |
| multilingual-e5-small-fp32 | janela800 | vetor | 0.841 / 0.876 / 0.897 | 0.825 / 0.853 / 0.895 | 0.841 | 86% |
| multilingual-e5-small-fp32 | janela400 | vetor | 0.843 / 0.877 / 0.899 | 0.836 / 0.848 / 0.885 | 0.861 | 93% |

O limiar foi escolhido olhando as próprias perguntas, então a acurácia dele é otimista.

## Latência (ms, CPU local)

| Modelo | Estratégia | Busca | Embedding da pergunta p50 / p95 | Busca no banco p50 / p95 |
|---|---|---|---|---|
| multilingual-e5-small-int8 | artigo | vetor | 5 / 8 | 1.8 / 5.1 |
| multilingual-e5-small-int8 | artigo_secao | vetor | 5 / 8 | 1.9 / 2.9 |
| multilingual-e5-small-int8 | artigo_sem_contexto | vetor | 5 / 8 | 1.6 / 2.1 |
| multilingual-e5-small-int8 | janela800 | vetor | 5 / 8 | 1.7 / 1.9 |
| multilingual-e5-small-int8 | janela400 | vetor | 5 / 8 | 2.2 / 2.4 |
| multilingual-e5-small-int8 | artigo | texto | 5 / 8 | 1.6 / 2.4 |
| multilingual-e5-small-int8 | artigo_secao | texto | 5 / 8 | 1.4 / 1.8 |
| multilingual-e5-small-int8 | artigo_sem_contexto | texto | 5 / 8 | 1.4 / 2.0 |
| multilingual-e5-small-int8 | janela800 | texto | 5 / 8 | 1.6 / 2.4 |
| multilingual-e5-small-int8 | janela400 | texto | 5 / 8 | 1.4 / 2.1 |
| multilingual-e5-small-int8 | artigo | hibrida | 5 / 8 | 2.4 / 3.2 |
| multilingual-e5-small-int8 | artigo_secao | hibrida | 5 / 8 | 2.1 / 2.4 |
| multilingual-e5-small-int8 | artigo_sem_contexto | hibrida | 5 / 8 | 2.0 / 2.6 |
| multilingual-e5-small-int8 | janela800 | hibrida | 5 / 8 | 2.1 / 2.6 |
| multilingual-e5-small-int8 | janela400 | hibrida | 5 / 8 | 2.5 / 3.2 |
| multilingual-e5-small-fp32 | artigo | vetor | 7 / 18 | 1.8 / 4.3 |
| multilingual-e5-small-fp32 | artigo_secao | vetor | 7 / 18 | 1.7 / 1.8 |
| multilingual-e5-small-fp32 | artigo_sem_contexto | vetor | 7 / 18 | 1.7 / 2.0 |
| multilingual-e5-small-fp32 | janela800 | vetor | 7 / 18 | 1.6 / 2.0 |
| multilingual-e5-small-fp32 | janela400 | vetor | 7 / 18 | 2.2 / 2.5 |

## Perguntas sem acerto no top 5

- multilingual-e5-small-int8 / artigo / vetor: r01, r02, r03, r09, r12, r15, r19, r26, r30, m02
- multilingual-e5-small-int8 / artigo_secao / vetor: r09, r12, r19, m02
- multilingual-e5-small-int8 / artigo_sem_contexto / vetor: r04, r09, r12, r19, r23
- multilingual-e5-small-int8 / janela800 / vetor: r02, r09, r10, r12, r13, r15, r17, r18, r23, r25, r30
- multilingual-e5-small-int8 / janela400 / vetor: r01, r02, r04, r09, r10, r11, r12, r13, r14, r15
- multilingual-e5-small-int8 / artigo / texto: r02, r03, r04, r06, r09, r12, r14, r19, r27, m02
- multilingual-e5-small-int8 / artigo_secao / texto: r02, r03, r04, r06, r09, r12, r14, r19, r27, m02
- multilingual-e5-small-int8 / artigo_sem_contexto / texto: r02, r03, r04, r06, r09, r12, r14, r19, r27, m02
- multilingual-e5-small-int8 / janela800 / texto: r02, r03, r10, r12, r14, r20, r27, r30
- multilingual-e5-small-int8 / janela400 / texto: r01, r02, r03, r04, r06, r09, r10, r12, r13, r14, r15, r20, r27, r30, m02
- multilingual-e5-small-int8 / artigo / hibrida: r01, r03, r04, r09, r12, r19, r27, r30
- multilingual-e5-small-int8 / artigo_secao / hibrida: r03, r04, r09, r12, r19, r27, m02
- multilingual-e5-small-int8 / artigo_sem_contexto / hibrida: r03, r04, r09, r12, r19, r27
- multilingual-e5-small-int8 / janela800 / hibrida: r02, r10, r12, r13, r25, r27, r30
- multilingual-e5-small-int8 / janela400 / hibrida: r01, r02, r04, r09, r10, r12, r13, r27
- multilingual-e5-small-fp32 / artigo / vetor: r01, r02, r03, r09, r12, r15, r19, r30, m02
- multilingual-e5-small-fp32 / artigo_secao / vetor: r09, r12, r19, r27, m02
- multilingual-e5-small-fp32 / artigo_sem_contexto / vetor: r09, r12, r19, r23
- multilingual-e5-small-fp32 / janela800 / vetor: r01, r02, r10, r12, r13, r15, r17, r18, r23, r25, r30
- multilingual-e5-small-fp32 / janela400 / vetor: r01, r02, r03, r04, r09, r10, r11, r12, r13, r14, r15, m02
