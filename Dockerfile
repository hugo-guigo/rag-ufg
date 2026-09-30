# Imagem da API. O modelo de embeddings entra no build, com a revisão fixada: o container não baixa
# nada ao subir, o que importa no cold start da nuvem.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/hf \
    HF_HUB_DISABLE_TELEMETRY=1 \
    PORT=8080

WORKDIR /app
COPY requirements-api.txt .
RUN pip install -r requirements-api.txt

COPY rag/__init__.py rag/embeddings.py rag/
RUN python -c "from huggingface_hub import hf_hub_download as baixar; \
from rag.embeddings import ARQUIVOS, REPOSITORIO, REVISAO; \
[baixar(REPOSITORIO, f, revision=REVISAO) for f in (ARQUIVOS['int8'], 'tokenizer.json')]"
ENV HF_HUB_OFFLINE=1

COPY rag rag
COPY api api
RUN useradd --uid 10001 --no-create-home app
USER app

EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn api.app:app --host 0.0.0.0 --port ${PORT}"]
