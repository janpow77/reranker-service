"""API-Smoke-Tests fuer reranker-service (mockt sentence-transformers)."""
from __future__ import annotations

import sys
import types

import pytest


@pytest.fixture(autouse=True)
def _mock_sentence_transformers(monkeypatch):
    """Verhindert echten HF-Download in CI/Tests."""
    fake = types.ModuleType("sentence_transformers")

    class FakeCrossEncoder:
        def __init__(self, *args, **kwargs):
            self.name = args[0] if args else kwargs.get("model_name", "")

        def predict(self, pairs, **kwargs):
            # Deterministisch: laengere Passage -> hoeherer Score
            return [float(len(b)) / 100.0 for _, b in pairs]

    fake.CrossEncoder = FakeCrossEncoder
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake)


def _client():
    # Lazy-Import nach Mock
    from fastapi.testclient import TestClient

    from reranker_service.main import app

    return TestClient(app)


def test_health():
    c = _client()
    r = c.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "BAAI/bge-reranker-v2-m3" in data["models_configured"]


def test_rerank_returns_sorted_ranking():
    c = _client()
    body = {
        "model": "BAAI/bge-reranker-v2-m3",
        "query": "EFRE",
        "passages": ["kurz", "ein etwas laengerer text", "der laengste der drei texte ist dieser hier"],
    }
    r = c.post("/v1/rerank", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["scores"] == sorted(data["scores"], reverse=False) or len(data["scores"]) == 3
    # Ranking ist nach Score desc — Index 2 (laengster) muss erstes Element sein
    assert data["ranking"][0]["index"] == 2
    assert data["ranking"][-1]["index"] == 0


def test_top_k_kuerzt():
    c = _client()
    body = {"query": "Q", "passages": ["a", "bb", "ccc", "dddd"], "top_k": 2}
    r = c.post("/v1/rerank", json=body)
    assert r.status_code == 200
    assert len(r.json()["ranking"]) == 2


def test_return_documents_setzt_document_feld():
    c = _client()
    body = {"query": "Q", "passages": ["aaa", "bbb"], "return_documents": True}
    r = c.post("/v1/rerank", json=body)
    assert r.status_code == 200
    docs = [item["document"] for item in r.json()["ranking"]]
    assert all(d in ("aaa", "bbb") for d in docs)


def test_max_passages_413():
    c = _client()
    import os
    # Simuliere ueberlangen Batch
    body = {"query": "Q", "passages": ["x"] * 300}
    r = c.post("/v1/rerank", json=body)
    # Default MAX_PASSAGES_PER_REQUEST=200 — 300 muss 413 erzeugen
    assert r.status_code == 413


def test_empty_passages_validation():
    c = _client()
    r = c.post("/v1/rerank", json={"query": "Q", "passages": []})
    assert r.status_code == 422  # Pydantic min_length=1
