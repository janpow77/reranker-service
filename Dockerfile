# reranker-service — Cross-Encoder fuer llm-router-Spokes (rerank-Capability).
#
# Image-Strategie:
# - Multi-Stage, am Ende nur Runtime + Wheel + vorgeladenes HF-Modell
# - CPU-only Torch (sentence-transformers braucht torch>=1.11). Bei GPU-Build
#   sollten Caller selbst auf das offizielle pytorch/pytorch-Basisimage
#   wechseln und CUDA-Layer drueberlegen.
# - Modell wird im Build-Step in /opt/hf_cache vorgeladen, damit der Container
#   beim ersten Start keinen HuggingFace-Download macht.

FROM python:3.11-slim AS deps

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# CPU-only Torch (~250 MB statt ~2 GB GPU-Variante). GPU-Builds nutzen
# stattdessen das default-PyPI-Index.
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
RUN pip install --index-url ${TORCH_INDEX_URL} torch==2.3.1+cpu || pip install torch==2.3.1

COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install .

# Modell vorladen — erspart den Cold-Start-Download im Produktivlauf.
ARG PRELOAD_MODEL=BAAI/bge-reranker-v2-m3
ENV HF_HOME=/opt/hf_cache
RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('${PRELOAD_MODEL}', max_length=512); print('preload ok:', '${PRELOAD_MODEL}')"


# --------- Runtime --------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/data/hf_cache \
    TRANSFORMERS_OFFLINE=0 \
    HF_HUB_DISABLE_TELEMETRY=1

RUN useradd --create-home --uid 1000 reranker
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Site-Packages aus dem deps-Stage uebernehmen.
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin/uvicorn /usr/local/bin/uvicorn

# Vorgeladenes Modell ins Default-Cache-Verzeichnis kopieren. Bind-Mount
# auf /data/hf_cache ueberschreibt das im Bedarfsfall.
COPY --from=deps /opt/hf_cache /opt/hf_cache_baked

COPY src/ /app/src/
ENV PYTHONPATH=/app/src

# /data/hf_cache wird beim ersten Start aus dem baked-Cache befuellt, falls leer.
RUN mkdir -p /data/hf_cache /opt/reranker && chown -R reranker:reranker /data /opt/reranker

USER reranker
WORKDIR /opt/reranker

EXPOSE 8004

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=120s \
    CMD curl -fsS http://127.0.0.1:8004/health || exit 1

# Beim Start: HF-Cache aus baked-Image kopieren, falls leer (idempotent).
ENTRYPOINT ["/bin/bash", "-c", "if [ -z \"$(ls -A /data/hf_cache 2>/dev/null)\" ] && [ -d /opt/hf_cache_baked ]; then cp -r /opt/hf_cache_baked/. /data/hf_cache/; fi; exec uvicorn reranker_service.main:app --host 0.0.0.0 --port ${RERANKER_PORT:-8004}"]
