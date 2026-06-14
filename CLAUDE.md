# reranker-service

Cross-Encoder-Reranker-Microservice. Wird vom **llm-router** als Spoke mit Capability `rerank` angesprochen (Cohere/Voyage-kompatible Rerank-API). Host-agnostisch deploybar (NUC/evo-x2/Desktop) im Tailscale-Netz; Apps reden nicht direkt mit dem Service, sondern über den llm-router.

## Tech-Stack

- **Sprache:** Python `>=3.11`
- **Framework:** FastAPI (`>=0.110`) + Uvicorn (`uvicorn[standard]`), Pydantic v2
- **ML:** sentence-transformers (`>=2.7,<3.5`) `CrossEncoder`, transformers (`>=4.40,<4.50`, gepinnt wegen NameError-Bug in 4.50), torch (CPU-only Build via `download.pytorch.org/whl/cpu`)
- **Default-Modell:** `BAAI/bge-reranker-v2-m3` (multilingual, deutsch-tauglich); weitere Modelle lazy-loaded
- **Port:** `8004`
- **Deployment:** Docker (Multi-Stage, baked HF-Cache) + Compose, Image `ghcr.io/janpow77/reranker-service`

## Setup & Befehle

```bash
# Install (editable, inkl. dev-Extras)
pip install -e ".[dev]"

# Lokal starten
uvicorn reranker_service.main:app --host 0.0.0.0 --port 8004
# (PYTHONPATH=src falls nicht installiert)

# Tests (mockt sentence-transformers, kein HF-Download)
pytest

# Lint
ruff check .

# Docker-Build (CPU, baked Modell) + Push
docker build -t ghcr.io/janpow77/reranker-service:v0.1 .
docker push ghcr.io/janpow77/reranker-service:v0.1

# Deploy CPU (env-File: /etc/reranker-service/env, Vorlage .env.example)
docker compose --env-file /etc/reranker-service/env up -d

# Deploy GPU (nvidia-container-toolkit nötig)
docker compose -f compose.yaml -f compose.gpu.yaml up -d

# Smoke-Test
curl -X POST http://127.0.0.1:8004/v1/rerank \
  -H 'Content-Type: application/json' \
  -d '{"query":"Test","passages":["Hallo Welt","Foo Bar"]}'
```

CI: `.github/workflows/image.yml` baut + pusht das Image nach GHCR (push auf `master`/`main`, Tags `v*.*.*`, manuell).

### Endpoints

- `GET /health` — Liveness inkl. geladene/konfigurierte Modelle
- `GET /v1/models` — OpenAI-Style Modell-Liste (capability `rerank`)
- `POST /v1/rerank` und `POST /rerank` (Alias) — Rerank, identischer Payload
- `GET /` — Service-Info

### Wichtige ENV-Variablen

`RERANKER_HOST` (`0.0.0.0`), `RERANKER_PORT` (`8004`), `RERANKER_DEVICE` (`cpu`|`cuda`), `RERANKER_DEFAULT_MODEL`, `RERANKER_PRELOAD_MODELS` (kommagetrennt), `RERANKER_API_KEY` (gesetzt → `X-Api-Key`-Header verlangt), `RERANKER_MAX_PASSAGES` (`200`), `RERANKER_MAX_PASSAGE_CHARS` (`8000`), `RERANKER_MAX_SEQ_LEN` (`512`), `RERANKER_EAGER_LOAD` (`true`), `HF_HOME` (`/data/hf_cache`). Vollständig in `.env.example` / `README.md`.

## Struktur

```
src/reranker_service/
  main.py        FastAPI-App: Endpoints, Schemas (RerankRequest/Response), API-Key-Dep, _do_rerank
  config.py      Config-Dataclass (frozen) aus ENV, Singleton via get_config()
  model.py       ModelRegistry: threadsicheres Lazy-Load der CrossEncoder, predict(); get_registry()
  __init__.py    __version__
tests/test_api.py  API-Smoke-Tests (sentence-transformers gemockt)
Dockerfile         Multi-Stage, baked BAAI/bge-reranker-v2-m3
compose.yaml       generisches Deploy (CPU)
compose.gpu.yaml   GPU-Override (RERANKER_DEVICE=cuda, nvidia)
.env.example       ENV-Vorlage
graphify-out/      Code-Graph-Artefakte (graph.json/html)
```

Zentrale Module (aus `graphify-out/graph.json`, nach Knoten-Grad): `main.py` (App + Routing, höchster Grad), `config.get_config()`, `main._do_rerank()`, `model.ModelRegistry` / `get_registry()`. Aufrufkette: Request → `_do_rerank` → `registry.predict()` → `ModelRegistry.get()` (Lazy-Load CrossEncoder).

## Konventionen

- **Lint/Format:** Ruff, `line-length = 100`, `target-version = py311`, Regeln `E,F,W,I,B,UP` (`E501` ignoriert). Config in `pyproject.toml`.
- **Tests:** pytest; Tests mocken `sentence_transformers`, sodass kein echter HuggingFace-Download nötig ist.
- **Sprache:** Code-Kommentare und Docstrings auf Deutsch (im vorhandenen Code teils ASCII-Umlaute `ae/oe/ue`).
- **Typisierung:** `from __future__ import annotations`, moderne Typ-Syntax (`str | None`).
