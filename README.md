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

## Phase 2 — Graph Service MVP

### Upsert nodes and edges

```bash
curl -X POST http://127.0.0.1:8000/graph/upsert \
  -H "Content-Type: application/json" \
  -d '{
    "nodes": [
      {"node_id": "ent:echogarden", "node_type": "Entity", "props": {"label": "EchoGarden"}},
      {"node_id": "ent:knowledge",  "node_type": "Entity", "props": {"label": "Knowledge"}}
    ],
    "edges": [
      {
        "from_node_id": "ent:echogarden",
        "to_node_id":   "ent:knowledge",
        "edge_type":    "ABOUT",
        "weight":       1.0,
        "provenance":   {"created_by": "manual", "confidence": 1.0, "migrated": false}
      }
    ]
  }'
```

### Query a node's neighbors

```bash
curl -X POST http://127.0.0.1:8000/graph/query \
  -H "Content-Type: application/json" \
  -d '{"node_id": "ent:echogarden", "direction": "both", "limit": 20}'
```

### Expand from a memory node (1-hop BFS)

```bash
# First ingest some text:
curl -X POST http://127.0.0.1:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"text": "EchoGarden is a local-first Knowledge garden built with FastAPI."}'

# Use the returned memory_id to expand:
curl -X POST http://127.0.0.1:8000/graph/expand \
  -H "Content-Type: application/json" \
  -d '{
    "seed_node_ids": ["mem:<MEMORY_ID>"],
    "hops": 1,
    "direction": "both",
    "max_nodes": 100,
    "max_edges": 200
  }'
```

### Expand with edge-type and time filters

```bash
curl -X POST http://127.0.0.1:8000/graph/expand \
  -H "Content-Type: application/json" \
  -d '{
    "seed_node_ids": ["ent:echogarden"],
    "hops": 2,
    "direction": "out",
    "edge_types": ["MENTIONS", "ABOUT"],
    "time_min": "2025-01-01T00:00:00",
    "max_nodes": 50
  }'
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
│       ├── graph/
│       │   ├── __init__.py
│       │   ├── models.py
│       │   └── service.py
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
│           ├── chat.py
│           └── graph.py
└── data/               (created at runtime, git-ignored)
```
