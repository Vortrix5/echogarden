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
│       │   └── config.py
│       ├── db/
│       │   ├── schema.sql
│       │   ├── migrate.py
│       │   └── conn.py
│       └── routers/
│           ├── health.py
│           └── cards.py
└── data/               (created at runtime, git-ignored)
```
