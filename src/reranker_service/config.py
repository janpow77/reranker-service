"""Konfiguration via Umgebungsvariablen.

Alle Optionen sind via ENV ueberschreibbar. Default-Werte zielen auf einen
CPU-only Lauf auf der NUC (Intel/AMD-CPU, kein GPU); fuer evo-x2 oder
Desktop einfach RERANKER_DEVICE=cuda setzen, sentence-transformers nimmt
dann automatisch das default-CUDA-Geraet.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.lower() in ("1", "true", "yes", "on")


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    if not raw:
        return list(default)
    return [s.strip() for s in raw.split(",") if s.strip()]


@dataclass(frozen=True)
class Config:
    # Server-Bind
    host: str = field(default_factory=lambda: os.environ.get("RERANKER_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.environ.get("RERANKER_PORT", "8004")))

    # Modell-Cache + Device
    model_cache_dir: str = field(
        default_factory=lambda: os.environ.get("HF_HOME", "/data/hf_cache"),
    )
    device: str = field(default_factory=lambda: os.environ.get("RERANKER_DEVICE", "cpu"))
    default_model: str = field(
        default_factory=lambda: os.environ.get(
            "RERANKER_DEFAULT_MODEL", "BAAI/bge-reranker-v2-m3",
        ),
    )

    # Liste vorgeladener Modelle (beim Startup). Schluessel wird im API gegen
    # ``model``-Feld aus dem Request geprueft.
    preload_models: list[str] = field(
        default_factory=lambda: _env_list(
            "RERANKER_PRELOAD_MODELS",
            ["BAAI/bge-reranker-v2-m3"],
        ),
    )

    # Auth: optional. Wenn API_KEY gesetzt → ``X-Api-Key``-Header verlangt.
    # Im Produktiv-Setup wird der Service typischerweise NUR aus dem
    # llm-router (Tailscale) erreicht; eine zusaetzliche API-Key-Schicht
    # ist optional aber empfohlen.
    api_key: str | None = field(default_factory=lambda: os.environ.get("RERANKER_API_KEY"))

    # Limits — Schutz vor Memory-Spikes bei riesigen Batches.
    max_passages_per_request: int = field(
        default_factory=lambda: int(os.environ.get("RERANKER_MAX_PASSAGES", "200")),
    )
    max_passage_chars: int = field(
        default_factory=lambda: int(os.environ.get("RERANKER_MAX_PASSAGE_CHARS", "8000")),
    )
    max_sequence_length: int = field(
        default_factory=lambda: int(os.environ.get("RERANKER_MAX_SEQ_LEN", "512")),
    )

    # Modell-Vor-Download: wenn True, laedt Service bei Startup; sonst Lazy.
    eager_load: bool = field(default_factory=lambda: _env_bool("RERANKER_EAGER_LOAD", True))


_singleton: Config | None = None


def get_config() -> Config:
    global _singleton
    if _singleton is None:
        _singleton = Config()
    return _singleton
