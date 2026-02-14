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

## Host Folder Capture

EchoGarden continuously watches a folder on your computer and automatically ingests any files you drop into it.

### Setup

1. **Create a watch folder** anywhere on your machine:

   ```bash
   mkdir ~/echogarden_watch
   ```

2. **Set the path** in your `.env` file:

   ```dotenv
   EG_HOST_WATCH_PATH=/Users/me/echogarden_watch
   ```

3. **Start the services:**

   ```bash
   docker compose up --build
   ```

4. **Drop a file** into the watch folder:

   ```bash
   echo "Hello EchoGarden" > ~/echogarden_watch/hello.txt
   ```

5. **Verify** capture (within ~2 seconds):

   ```bash
   # Check watcher status and job counts
   curl http://127.0.0.1:8000/capture/status

   # List recent jobs
   curl http://127.0.0.1:8000/capture/jobs

   # See the created memory card
   curl http://127.0.0.1:8000/cards
   ```

### How It Works

- A **polling watcher** scans the mounted folder every 2 seconds (configurable via `EG_POLL_INTERVAL`).
- New or modified files are hashed (streaming SHA-256), registered as `source` + `blob` rows, and a `job` is enqueued.
- A **background worker** picks up queued jobs and creates `MEMORY_CARD` entries:
  - **Text files** (`.txt`, `.md`, `.json`, `.csv`, `.log`): full content summary.
  - **Binary / large files** (> 20 MB): placeholder card with metadata.
- Hidden files, directories, and system folders are automatically skipped.
- Duplicate detection is based on `mtime_ns + size_bytes` — unchanged files are ignored.

### Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `EG_HOST_WATCH_PATH` | `./host_watch` | Absolute path to watch folder on host |
| `EG_POLL_INTERVAL` | `2` | Seconds between scans |
| `EG_MAX_FILE_MB` | `20` | Max file size (MB) for content reading |

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/capture/status` | GET | Watch roots, poll interval, job counts |
| `/capture/jobs` | GET | List jobs (filter: `?status=queued\|done\|error&limit=50`) |

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
│       │   ├── schema_capture.sql
│       │   ├── migrate.py
│       │   ├── conn.py
│       │   └── repo.py
│       ├── capture/
│       │   ├── config.py
│       │   ├── hasher.py
│       │   ├── repo.py
│       │   └── watcher.py
│       ├── workers/
│       │   └── job_worker.py
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
│           ├── capture.py
│           ├── chat.py
│           └── graph.py
├── host_watch/          (default local watch folder)
└── data/                (created at runtime, git-ignored)
```
