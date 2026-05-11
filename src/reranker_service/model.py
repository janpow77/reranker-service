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
            log.info("Lade Cross-Encoder %s (device=%s, HF_HOME=%s)…", model_name, cfg.device, cfg.model_cache_dir)
            # sentence-transformers nimmt HF_HOME aus dem ENV automatisch.
            # Kein cache_folder-Argument — wurde in spaeteren Versionen ent-
            # fernt/umbenannt; ENV ist die stabile Schnittstelle.
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
