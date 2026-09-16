# Architektur — reranker-service

_Automatisch generiert von graphify-kira aus dem Code-Graphen. Nicht von Hand editieren — wird beim nächsten Lauf überschrieben._

**Umfang:** 50 Knoten, 86 Kanten, 7 größere Module, 0 zirkuläre Abhängigkeiten.

## Modulkarte

- **Reranking Service** (11): `__init__.py`, `main.py`, `model.py`
- **Smoke Tests** (11): `test_api.py`
- **Config Management** (8): `config.py`, `model.py`
- **Model Registry** (7): `model.py`
- **Rerank API** (6): `main.py`
- **Rerank Models** (4): `BaseModel`, `main.py`
- **Rerank Request** (3): `main.py`

## Zentrale Bausteine (God Nodes)

_Hohe Zentralität ist nicht automatisch ein Defekt (zentrale Stores/Modelle sind oft legitim). Konkrete Refactoring-Prioritäten siehe Optimierungs-Report._

- `_client() (tests/test_api.py)` — Grad 7 (ein 7/aus 0)
- `get_config() (src/reranker_service/config.py)` — Grad 10 (ein 9/aus 1)
- `main.py (src/reranker_service/main.py)` — Grad 18 (ein 1/aus 17)
- `ModelRegistry (src/reranker_service/model.py)` — Grad 7 (ein 3/aus 4)
- `Config (src/reranker_service/config.py)` — Grad 2 (ein 2/aus 0)
- `get_registry() (src/reranker_service/model.py)` — Grad 7 (ein 6/aus 1)
- `BaseModel` — Grad 3 (ein 3/aus 0)
- `RerankRequest (src/reranker_service/main.py)` — Grad 7 (ein 5/aus 2)
- `test_api.py (tests/test_api.py)` — Grad 9 (ein 1/aus 8)
- `config.py (src/reranker_service/config.py)` — Grad 7 (ein 3/aus 4)

## Schnittstellen / Brücken (Betweenness)

- `ModelRegistry (src/reranker_service/model.py)` — Betweenness 0.031
- `get_registry() (src/reranker_service/model.py)` — Betweenness 0.023
- `main.py (src/reranker_service/main.py)` — Betweenness 0.013
- `_do_rerank() (src/reranker_service/main.py)` — Betweenness 0.011
- `.get() (src/reranker_service/model.py)` — Betweenness 0.009
- `v1_rerank() (src/reranker_service/main.py)` — Betweenness 0.008
- `model.py (src/reranker_service/model.py)` — Betweenness 0.008
- `get_config() (src/reranker_service/config.py)` — Betweenness 0.006
- `config.py (src/reranker_service/config.py)` — Betweenness 0.006
- `RerankRequest (src/reranker_service/main.py)` — Betweenness 0.004

## Empfohlene Spezialisten

Passend zu Stack/Domäne dieses Projekts (Claude-Code-Agents/Skills):

`/deutsche-formulierung`, `@git-workflow`, `/auto-verify`, `/rag-knowledge-base`, `@code-api-checker`, `@code-audit-expert`, `@docker-proxy-debugger`, `/docker-debug`, `/cross-project-health`, `@memory-bridge`.

## Hinweis für Änderungen

Vor dem Ändern eines zentralen Bausteins die Abhängigen prüfen — am schnellsten über den **graphify-MCP** (globaler Graph): „Was hängt an `<datei>`?". Brücken-Knoten stabil halten.

