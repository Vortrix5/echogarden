# EchoGarden

Local-first personal knowledge garden with memory cards, entity extraction, and semantic search.

## Quick Start

```bash
# 1. Create your .env from the example
cp .env.example .env

# 2. Build and start all services
docker compose up --build
```

## Verify

```bash
# Health check (SQLite + Qdrant status)
curl http://127.0.0.1:8000/healthz

# List memory cards (empty initially)
curl http://127.0.0.1:8000/cards

# Swagger UI
open http://127.0.0.1:8000/docs
```

## Phase 1 — Tool Registry & Passive Core-Agents

### List registered tools

```bash
curl http://127.0.0.1:8000/tools
```

### Get a tool's schema

```bash
curl http://127.0.0.1:8000/tools/retrieval/schema
```

### Run the retrieval tool directly

```bash
curl -X POST http://127.0.0.1:8000/tools/retrieval/run \
  -H "Content-Type: application/json" \
  -d '{
    "callee": "retrieval",
    "inputs": {"query": "hello", "limit": 5}
  }'
```

### Ingest text (creates a memory card)

```bash
curl -X POST http://127.0.0.1:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"text": "EchoGarden is a local-first knowledge garden that helps you remember everything."}'
```

### Chat (retrieval + weaver + verifier)

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_text": "What is EchoGarden?"}'
```

## Services

| Service | URL | Description |
|---------|-----|-------------|
| API | http://127.0.0.1:8000 | FastAPI backend |
| Qdrant | http://127.0.0.1:6333 | Vector search engine |
| Swagger | http://127.0.0.1:8000/docs | Interactive API docs |

## Data

All persistent data is stored in `./data/` on the host:

- `data/sqlite/echogarden.db` — SQLite database
- `data/qdrant/` — Qdrant vector storage

## Reset

```bash
# Stop services and wipe all data
docker compose down
rm -rf data/

# Rebuild from scratch
docker compose up --build
```

## Project Structure

```
├── docker-compose.yml
├── .env.example
├── api/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py
│       ├── core/
│       │   ├── config.py
│       │   ├── tool_contracts.py
│       │   └── tool_registry.py
│       ├── db/
│       │   ├── schema.sql
│       │   ├── migrate.py
│       │   ├── conn.py
│       │   └── repo.py
│       ├── agents/
│       │   ├── base.py
│       │   ├── doc_parse.py
│       │   ├── ocr.py
│       │   ├── asr.py
│       │   ├── vision_embed.py
│       │   ├── text_embed.py
│       │   ├── retrieval.py
│       │   ├── graph_builder.py
│       │   ├── weaver.py
│       │   └── verifier.py
│       └── routers/
│           ├── health.py
│           ├── cards.py
│           ├── tools.py
│           ├── ingest.py
│           └── chat.py
└── data/               (created at runtime, git-ignored)
```
