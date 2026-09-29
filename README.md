# Assistente do regulamento da UFG (RAG + agente)

Em construção. O README completo, com arquitetura, avaliação e limitações, entra na última etapa.

Feito até agora:

- Download dos PDFs públicos com conferência de SHA-256 (`fontes.json`).
- Extração do texto do RGCG (Resolução CEPEC 1791/2022) com página, artigo e seção de cada parágrafo.
- Duas estratégias de divisão em trechos: por artigo e por janela fixa de 800 caracteres.

```bash
python -m venv .venv
.venv/Scripts/activate        # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
python -m rag.fontes          # baixa os PDFs para dados/pdfs/
python scripts/ver_trechos.py # estatísticas dos trechos
pytest
```
