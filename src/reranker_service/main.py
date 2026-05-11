"""FastAPI-App fuer reranker-service.

Endpunkte:
  POST /rerank         — kompakte interne Form
  POST /v1/rerank      — llm-router-kompatible Variante (gleicher Payload)
  GET  /health         — Liveness/Readiness inkl. geladene Modelle
  GET  /v1/models      — Liste der praeloadeten Modelle
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import __version__
from .config import get_config
from .model import get_registry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
log = logging.getLogger("reranker-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_config()
    reg = get_registry()
    log.info(
        "reranker-service %s — host=%s:%d device=%s eager_load=%s",
        __version__, cfg.host, cfg.port, cfg.device, cfg.eager_load,
    )
    if cfg.eager_load:
        for m in cfg.preload_models:
            try:
                reg.get(m)
            except Exception as exc:  # noqa: BLE001
                log.error("Preload von %s fehlgeschlagen: %s", m, exc)
    yield
    log.info("reranker-service stoppt.")


app = FastAPI(
    title="reranker-service",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def _require_api_key(request: Request) -> None:
    cfg = get_config()
    if not cfg.api_key:
        return
    provided = request.headers.get("x-api-key") or request.headers.get("X-Api-Key")
    if not provided or provided != cfg.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid api key")


# ---------- Schemas ----------


class RerankRequest(BaseModel):
    """OpenAI-Cohere-aehnliches Schema.

    Beispiel:
      {
        "model": "bge-reranker-v2-m3",
        "query": "EFRE Foerderbescheid Auflagen",
        "passages": ["Auflage 1: …", "Auflage 2: …", "Belege: …"],
        "top_k": 5,
        "return_documents": false
      }
    """

    model_config = ConfigDict(protected_namespaces=())

    model: str | None = Field(default=None, description="Modell-ID; default aus Server-Config.")
    query: str = Field(min_length=1)
    passages: list[str] = Field(min_length=1)
    top_k: int | None = Field(default=None, ge=1)
    return_documents: bool = False

    @field_validator("passages")
    @classmethod
    def _strip_passages(cls, v: list[str]) -> list[str]:
        return [p if p is not None else "" for p in v]


class RankedItem(BaseModel):
    index: int
    score: float
    document: str | None = None


class RerankResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model: str
    duration_ms: int
    scores: list[float]  # Reihenfolge wie Input-passages
    ranking: list[RankedItem]  # nach score desc sortiert, optional gekuerzt auf top_k


# ---------- Endpoints ----------


@app.get("/health")
async def health() -> dict:
    cfg = get_config()
    reg = get_registry()
    return {
        "status": "ok",
        "version": __version__,
        "device": cfg.device,
        "default_model": cfg.default_model,
        "models_loaded": reg.loaded_models(),
        "models_configured": cfg.preload_models,
    }


@app.get("/v1/models")
async def list_models(_=Depends(_require_api_key)) -> dict:
    """OpenAI-kompatible Modell-Liste; llm-router kann damit Spoke-Capabilities pruefen."""
    cfg = get_config()
    reg = get_registry()
    # Ausgeben werden NUR geladene + konfigurierte Modelle; lazy-loaded sind enthalten sobald
    # erstmals gefragt.
    names = sorted(set(reg.loaded_models()) | set(cfg.preload_models))
    return {
        "object": "list",
        "data": [
            {"id": n, "object": "model", "owned_by": "reranker-service", "capabilities": ["rerank"]}
            for n in names
        ],
    }


def _do_rerank(payload: RerankRequest) -> RerankResponse:
    cfg = get_config()
    reg = get_registry()

    if len(payload.passages) > cfg.max_passages_per_request:
        raise HTTPException(
            status_code=413,
            detail=f"too many passages ({len(payload.passages)} > {cfg.max_passages_per_request})",
        )
    # Truncate ueberlange passages defensiv — sentence-transformers kuerzt sowieso auf
    # max_seq_len Tokens, aber bei riesigen Strings frisst Tokenizer Zeit/RAM.
    capped_passages = [
        (p if len(p) <= cfg.max_passage_chars else p[: cfg.max_passage_chars])
        for p in payload.passages
    ]
    model_name = payload.model or cfg.default_model

    t0 = time.monotonic()
    try:
        scores = reg.predict(model_name, [(payload.query, p) for p in capped_passages])
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"model not available: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("Rerank failed for %s", model_name)
        raise HTTPException(status_code=500, detail=f"rerank failed: {exc}") from exc
    dur_ms = int((time.monotonic() - t0) * 1000)

    # Sortierung nach Score desc; idx zeigt auf Original-Position.
    pairs = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
    if payload.top_k is not None:
        pairs = pairs[: payload.top_k]
    ranking = [
        RankedItem(
            index=i,
            score=s,
            document=payload.passages[i] if payload.return_documents else None,
        )
        for i, s in pairs
    ]

    return RerankResponse(
        model=model_name,
        duration_ms=dur_ms,
        scores=scores,
        ranking=ranking,
    )


@app.post("/rerank", response_model=RerankResponse)
async def rerank(
    payload: RerankRequest,
    _: Annotated[None, Depends(_require_api_key)] = None,
) -> RerankResponse:
    return _do_rerank(payload)


@app.post("/v1/rerank", response_model=RerankResponse)
async def v1_rerank(
    payload: RerankRequest,
    _: Annotated[None, Depends(_require_api_key)] = None,
) -> RerankResponse:
    """Alias mit /v1/-Prefix fuer Konsistenz mit OpenAI-Style Routen im llm-router."""
    return _do_rerank(payload)


@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {
        "service": "reranker-service",
        "version": __version__,
        "endpoints": ["/health", "/v1/models", "/rerank", "/v1/rerank"],
    }
