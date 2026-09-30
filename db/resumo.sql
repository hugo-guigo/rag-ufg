-- Resumo do log da API por dia (etapa 6). Rodar: python scripts/resumo_consultas.py [--dias 7]
-- Latência e tokens só das perguntas respondidas (status 200); erros e bloqueios contados à parte.
SELECT
    (criado_em AT TIME ZONE 'America/Sao_Paulo')::date                            AS dia,
    count(*)                                                                      AS perguntas,
    count(*) FILTER (WHERE status = 200)                                          AS respondidas,
    count(*) FILTER (WHERE status = 429)                                          AS bloqueadas_limite,
    count(*) FILTER (WHERE status >= 500)                                         AS com_erro,
    count(DISTINCT cliente)                                                       AS clientes,
    round(percentile_cont(0.5) WITHIN GROUP (ORDER BY ms_total) FILTER (WHERE status = 200)) AS p50_ms,
    round(percentile_cont(0.95) WITHIN GROUP (ORDER BY ms_total) FILTER (WHERE status = 200)) AS p95_ms,
    round(avg(tokens_entrada) FILTER (WHERE status = 200))                        AS tokens_entrada_medio,
    round(avg(tokens_saida) FILTER (WHERE status = 200))                          AS tokens_saida_medio,
    round(avg(chamadas_llm) FILTER (WHERE status = 200), 1)                       AS chamadas_llm_media,
    count(*) FILTER (WHERE 'buscar_regulamento' = ANY (ferramentas))              AS usaram_regulamento,
    count(*) FILTER (WHERE 'consultar_calendario' = ANY (ferramentas))            AS usaram_calendario,
    count(*) FILTER (WHERE cobertura = 'nenhuma')                                 AS nao_sei,
    sum(erros_ferramenta)                                                         AS erros_ferramenta,
    count(*) FILTER (WHERE forcou_resposta)                                       AS respostas_forcadas
FROM consultas
WHERE criado_em > now() - make_interval(days => %(dias)s)
GROUP BY 1
ORDER BY 1 DESC;
