# Assistente do regulamento da UFG (RAG + agente)

Em construção. O README completo, com arquitetura, avaliação e limitações, entra na última etapa.

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
