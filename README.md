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
