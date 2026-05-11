"""Modell-Loader + Inference. Threadsafe via Lock, mehrere Modelle parallel."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from sentence_transformers import CrossEncoder

from .config import get_config

log = logging.getLogger(__name__)


class ModelRegistry:
    """Haelt geladene Cross-Encoder im RAM. Lazy-Load mit Lock."""

    def __init__(self) -> None:
        self._models: dict[str, CrossEncoder] = {}
        self._load_lock = threading.Lock()

    def loaded_models(self) -> list[str]:
        return list(self._models.keys())

    def get(self, model_name: str) -> CrossEncoder:
        if model_name in self._models:
            return self._models[model_name]
        with self._load_lock:
            if model_name in self._models:
                return self._models[model_name]
            cfg = get_config()
            t0 = time.monotonic()
            # Sicherstellen dass sentence-transformers/huggingface den
            # konfigurierten Cache-Pfad benutzt — auch wenn der Caller die
            # ENV-Var nicht selbst gesetzt hat (z.B. lokaler systemd-Service,
            # devshell). Im Docker-Container ist HF_HOME bereits per ENV
            # gesetzt; setdefault ueberschreibt das nicht.
            import os as _os
            _os.environ.setdefault("HF_HOME", cfg.model_cache_dir)
            # transformers benutzt noch TRANSFORMERS_CACHE als zusaetzlichen
            # Fallback in aelteren Versionen.
            _os.environ.setdefault("TRANSFORMERS_CACHE", cfg.model_cache_dir)
            log.info(
                "Lade Cross-Encoder %s (device=%s, HF_HOME=%s)…",
                model_name, cfg.device, _os.environ.get("HF_HOME"),
            )
            model = CrossEncoder(
                model_name,
                max_length=cfg.max_sequence_length,
                device=cfg.device,
            )
            # Warmup mit kurzer Eingabe, damit Tokenizer + Forward-Pass JIT-warm sind.
            try:
                model.predict([("warmup", "warmup")])
            except Exception as exc:  # noqa: BLE001
                log.warning("Warmup-Predict fuer %s fehlgeschlagen: %s", model_name, exc)
            self._models[model_name] = model
            log.info("Modell %s geladen in %.1fs", model_name, time.monotonic() - t0)
            return model

    def predict(self, model_name: str, pairs: list[tuple[str, str]]) -> list[float]:
        if not pairs:
            return []
        model = self.get(model_name)
        # sentence-transformers gibt numpy.ndarray oder list zurueck — beides handhaben.
        try:
            scores: Any = model.predict(pairs, show_progress_bar=False, convert_to_numpy=True)
        except TypeError:
            # Mock / aeltere CrossEncoder ohne show_progress_bar-Param
            scores = model.predict(pairs)
        if hasattr(scores, "tolist"):
            scores = scores.tolist()
        return [float(s) for s in scores]


_registry: ModelRegistry | None = None
_registry_lock = threading.Lock()


def get_registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = ModelRegistry()
    return _registry
