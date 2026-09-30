# Assistente do regulamento da UFG (RAG + agente)

Em construção. O README completo, com arquitetura, avaliação e limitações, entra na última etapa.

**Demo:** [ca-rag-ufg.kindpond-1fdbf9ec.northcentralus.azurecontainerapps.io](https://ca-rag-ufg.kindpond-1fdbf9ec.northcentralus.azurecontainerapps.io)
(Azure Container Apps + Neon + Groq, no plano gratuito de cada um; limite de 50 perguntas por dia no total).

Feito até agora:

- Download dos PDFs públicos com conferência de SHA-256 (`fontes.json`).
- Extração do texto do RGCG (Resolução CEPEC 1791/2022) com página, artigo e seção de cada parágrafo.
- Duas estratégias de divisão em trechos: por artigo e por janela fixa de 800 caracteres.
- Calendário 2026 (Resolução CEPEC 1966/2025) extraído para `dados/calendario_2026.csv` (179 eventos).
- Embeddings com multilingual-e5-small (ONNX int8, sem PyTorch) no PostgreSQL com pgvector.
- Agente com tool calling (`rag/agente.py`): o modelo escolhe entre buscar no regulamento e consultar o
  calendário (busca híbrida com filtro de datas), com limite de 4 passos e erros de ferramenta devolvidos
  ao modelo. Avaliação em `resultados/agente.md`.

```bash
python scripts/perguntar.py "quantas vezes posso trancar e qual o prazo em 2027/1?" --agente
```

- API em FastAPI (`POST /perguntar`, `GET /health`) em container, com o modelo de embeddings dentro da
  imagem. Cada pergunta vira uma linha na tabela `consultas` (latência, tokens, ferramentas, erros), que
  também conta o limite de requisições: 5 por minuto e 30 por dia por cliente (hash do IP com sal, sem
  guardar o IP) e 50 por dia no total, que é o que cabe no limite diário de tokens do plano grátis do Groq.

```bash
python scripts/gerar_env.py                     # acrescenta SAL_CLIENTE a um .env existente
python scripts/preparar_banco.py                # cria a tabela consultas e as permissões
docker compose --profile api up -d --build      # API em http://127.0.0.1:8000 (docs em /docs)
python scripts/resumo_consultas.py              # resumo do log por dia (db/resumo.sql)
```

- Deploy no Azure Container Apps (North Central US, escala até zero) com infraestrutura em Bicep
  (`infra/`), alerta de orçamento de US$ 1/mês criado antes de tudo e banco no Neon (AWS us-east-1).
  O GitHub Actions testa, constrói e testa a imagem, publica no GitHub Container Registry e troca a
  imagem do app por OIDC, com uma identidade que só tem permissão no próprio app. Nenhuma chave no
  repositório: os segredos ficam no Container App, e o `.env` local não vai para o Git.
  Medido em 30/09/2026: depois de ~5 min sem uso o app vai a zero réplicas; a primeira chamada a
  `/health` levou 6,5 s (cold start do container e, provavelmente, o Neon acordando) e as seguintes 0,64 s.

```bash
python scripts/preparar_neon.py                 # schema, usuário app e ingestão no Neon
python scripts/deploy_azure.py orcamento        # alerta de orçamento (antes de qualquer recurso)
python scripts/deploy_azure.py infra            # grupo, Container Apps e identidade de deploy
```

```bash
python -m venv .venv
.venv/Scripts/activate        # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/gerar_env.py   # .env com senhas aleatórias
docker compose up -d --wait   # Postgres 17 + pgvector em 127.0.0.1:5433
python scripts/ingerir.py     # PDFs -> trechos -> embeddings -> banco
python scripts/buscar.py "posso trancar a matrícula?"
pytest                                    # testes sem banco
RODAR_INTEGRACAO=1 pytest -m integracao   # testes com o banco
```
