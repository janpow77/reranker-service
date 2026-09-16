# reranker-service

Cross-Encoder-Reranker-Microservice. Wird vom **llm-router** als Spoke mit
Capability `rerank` angesprochen — analog zu Ollama-Chat/Embeddings.

Deploybar auf beliebigem GPU/CPU-Host im Tailscale-Netz (NUC, evo-x2,
Desktop). Apps (audit_designer, flowinvoice, …) reden **nicht direkt** mit
diesem Service — sie sprechen den llm-router, der dann an den passenden
reranker-service-Spoke proxiet.

## Architektur

```
   audit_designer   flowinvoice   workshop
        │               │             │
        └──── X-App-Id ─┴──── X-Api-Key
                       ▼
              llm-router (CCX23, :7842)
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
     ollama       egpu-managerd   reranker-service
   (chat, embed)  (gpu-switch)     (cross-encoder)
       NUC            NUC            NUC/evo/Desktop
```

## API

Identisch zu Cohere/Voyage-Rerank-API. Beispiel:

```http
POST /v1/rerank
Content-Type: application/json
X-Api-Key: <optional>

{
  "model": "BAAI/bge-reranker-v2-m3",
  "query": "EFRE Foerderbescheid Auflagen",
  "passages": [
    "Auflage 1: Beleg jeder Ausgabe …",
    "Allgemeine Verpflichtung zur Kommunikation …",
    "Kontoauszug aus dem Vorhaben-Konto …"
  ],
  "top_k": 5,
  "return_documents": false
}
```

Antwort:

```json
{
  "model": "BAAI/bge-reranker-v2-m3",
  "duration_ms": 38,
  "scores": [0.92, 0.41, 0.78],
  "ranking": [
    {"index": 0, "score": 0.92, "document": null},
    {"index": 2, "score": 0.78, "document": null},
    {"index": 1, "score": 0.41, "document": null}
  ]
}
```

### Endpoints

| Methode | Pfad | Zweck |
|---------|------|-------|
| GET | `/health` | Liveness inkl. geladene Modelle |
| GET | `/v1/models` | OpenAI-Style Modell-Liste (capability `rerank`) |
| POST | `/v1/rerank` | Rerank (von llm-router proxied) |
| POST | `/rerank` | Alias ohne `/v1`-Prefix |

## Modelle

Default-Preload: `BAAI/bge-reranker-v2-m3` (568 MB, multilingual,
deutsch-tauglich). Über `RERANKER_PRELOAD_MODELS` kommagetrennt mehrere:

```bash
RERANKER_PRELOAD_MODELS=BAAI/bge-reranker-v2-m3,cross-encoder/ms-marco-MiniLM-L-6-v2
```

`bge-reranker-v2-m3` → audit_designer + workshop (Memory-Modul)
`cross-encoder/ms-marco-MiniLM-L-6-v2` → flowinvoice (englisch-Standard MS-MARCO)

Lazy-Load: weitere Modelle werden beim ersten Request automatisch geladen.

## Konfiguration

| ENV | Default | Zweck |
|-----|---------|-------|
| `RERANKER_HOST` | `0.0.0.0` | Listen-Adresse |
| `RERANKER_PORT` | `8004` | Port |
| `RERANKER_DEVICE` | `cpu` | `cpu` / `cuda` / `cuda:0` |
| `RERANKER_DEFAULT_MODEL` | `BAAI/bge-reranker-v2-m3` | Fallback wenn Request kein `model` setzt |
| `RERANKER_PRELOAD_MODELS` | `BAAI/bge-reranker-v2-m3` | Komma-getrennt, beim Startup laden |
| `RERANKER_API_KEY` | _leer_ | Wenn gesetzt → `X-Api-Key` Header verlangt |
| `RERANKER_MAX_PASSAGES` | `200` | Limit pro Request |
| `RERANKER_MAX_SEQ_LEN` | `512` | Token-Truncation |
| `RERANKER_EAGER_LOAD` | `true` | Modelle beim Startup laden |
| `HF_HOME` | `/data/hf_cache` | HuggingFace-Cache-Verzeichnis |

## Deployment

### Build + Push

```bash
# CPU-Build (Default, ~3 GB Image inkl. baked Modell)
docker build -t ghcr.io/janpow77/reranker-service:v0.1 .
docker push ghcr.io/janpow77/reranker-service:v0.1

# GPU-Build (Caller stellt CUDA-Basisimage selbst — Dockerfile.gpu nicht im Repo)
```

### Auf dem NUC starten

```bash
sudo mkdir -p /var/lib/reranker/data
sudo chown 1000:1000 /var/lib/reranker/data
cp .env.example /etc/reranker-service/env
# /etc/reranker-service/env editieren — RERANKER_API_KEY setzen
docker compose --env-file /etc/reranker-service/env up -d
```

### GPU-Variante (z.B. evo-x2 mit RTX 5070 Ti)

```bash
docker compose -f compose.yaml -f compose.gpu.yaml up -d
```

## llm-router-Integration

Nach Deploy einen Spoke im llm-router-Admin anlegen:

```yaml
# in config.yaml oder via Admin-UI:
spokes:
  - name: nuc-reranker
    base_url: http://100.102.132.11:8004
    type: openai             # /v1/rerank-kompatibel
    capabilities: [rerank]
    enabled: true
    priority: 10

routes:
  - model_glob: "*reranker*"
    spoke_id: <id-of-nuc-reranker>
  - model_glob: "cross-encoder/*"
    spoke_id: <id-of-nuc-reranker>
```

Apps sprechen ab dann `https://llm-router.intern/v1/rerank` mit ihren
gewohnten Headern (`X-App-Id`, `X-Api-Key`) — Router routet automatisch.

## Smoke-Test

```bash
# Direkt am Service (Tailscale)
curl -X POST http://100.102.132.11:8004/v1/rerank \
  -H 'Content-Type: application/json' \
  -d '{"query":"Test","passages":["Hallo Welt","Foo Bar"]}'

# Über llm-router
curl -X POST http://llm-router.tailec75b1.ts.net:7842/v1/rerank \
  -H 'Content-Type: application/json' \
  -H 'X-App-Id: audit_designer' \
  -d '{"model":"BAAI/bge-reranker-v2-m3","query":"Test","passages":["a","b"]}'
```


## NUC: GPU-Betrieb seit dem 16.09.2026

Auf der NUC lief der Dienst bis zum 16.09.2026 mit CPU-Torch und brauchte bei
Last 14 auf 20 Kernen **4,4–4,7 s für zwei kurze Passagen** — ein fester
Preis je Anfrage, der den Reranker in der Memory-Suche unbrauchbar machte
(1-s-Budget, siehe audit_designer `memory_search.py`). Auf der internen
RTX 5060 (8 GB, Blackwell sm_120) sind es **40 ms für acht Passagen**.

Blackwell braucht torch ≥ 2.7 mit CUDA 12.8; der Bau nimmt die neuen
Build-Argumente:

```bash
docker build \
  --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/cu128 \
  --build-arg TORCH_SPEC=torch==2.7.1 \
  -t reranker-service:gpu .
```

Der Container auf der NUC wurde nicht per Compose, sondern per `docker run`
gestartet (Netz `spoke-stack_default`, damit der ai-router ihn als
`reranker-service:8004` findet):

```bash
docker run -d --name reranker-service --network spoke-stack_default \
  -p 8004:8004 -v /var/lib/reranker/data:/data --restart unless-stopped \
  --gpus all \
  -e RERANKER_DEVICE=cuda -e RERANKER_PORT=8004 -e HF_HOME=/data/hf_cache \
  -e RERANKER_DEFAULT_MODEL=BAAI/bge-reranker-v2-m3 \
  -e RERANKER_PRELOAD_MODELS=BAAI/bge-reranker-v2-m3 -e RERANKER_EAGER_LOAD=true \
  -e HF_HUB_DISABLE_TELEMETRY=1 -e TRANSFORMERS_OFFLINE=0 \
  reranker-service:gpu
```

Rückfall: der alte CPU-Container liegt gestoppt als `reranker-service-cpu`
(`docker stop reranker-service && docker rename … && docker start
reranker-service-cpu`). Das GHCR-Abbild `:latest` bleibt die CPU-Variante;
das GPU-Abbild ist lokal gebaut und nicht in der CI.
