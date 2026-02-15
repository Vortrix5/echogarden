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

## Phase 3 — Active Orchestrator + Execution Graph

### How it works

1. **File ingestion** — when a file is dropped into the watch folder, the watcher enqueues a job with a `trace_id`. The worker delegates to `Orchestrator.ingest_blob()` which:
   - Chooses a tool route based on MIME/extension: `doc_parse`, `ocr`, or `asr`
   - Dispatches each tool via the Tool Registry (not calling tool classes directly)
   - Writes `TOOL_CALL`, `EXEC_NODE`, `EXEC_EDGE` for every step
   - Creates an `EXEC_TRACE` record wrapping the full pipeline
   - Commits a `MEMORY_CARD` and upserts graph nodes/edges

2. **Chat** — `POST /chat` delegates to `Orchestrator.chat()`:
   - Security check (rejects binary/overly-long input)
   - `retrieval` → `weaver` → `verifier`
   - If Ollama is configured, weaver and verifier use the LLM; otherwise stub fallback
   - Persists `CONVERSATION_TURN` with `trace_id`
   - Full execution graph written

3. **Idempotency** — if a job is retried with the same `blob_id`, no duplicate memory card is created.

### Inspect execution traces

```bash
# After dropping a file, get the trace_id from job logs or /capture/jobs
curl http://127.0.0.1:8000/exec/<TRACE_ID>
```

Response includes `nodes` (which tools ran, their status, timing) and `edges` (dependencies between steps).

### List tool calls

```bash
# All recent tool calls
curl http://127.0.0.1:8000/tool_calls?limit=20

# Filter by trace
curl "http://127.0.0.1:8000/tool_calls?trace_id=<TRACE_ID>"
```

### Test: File ingestion trace

```bash
# 1. Drop a text file
echo "Phase 3 orchestrator test" > ~/echogarden_watch/test_phase3.txt

# 2. Wait 3 seconds, then check jobs
curl http://127.0.0.1:8000/capture/jobs?limit=1

# 3. Get the trace_id from the job payload, then:
curl http://127.0.0.1:8000/exec/<TRACE_ID>
# You should see nodes for: doc_parse, text_embed, graph_builder
```

### Test: Chat trace

```bash
# 1. Send a chat message
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_text": "What is EchoGarden?"}'

# 2. Use the trace_id from the response to inspect:
curl http://127.0.0.1:8000/exec/<TRACE_ID>
# You should see nodes for: retrieval, weaver, verifier
```

### Enable Ollama (optional LLM)

1. Install [Ollama](https://ollama.ai/) on your host machine
2. Pull a model: `ollama pull phi3:mini`
3. Add to your `.env`:

```dotenv
EG_OLLAMA_URL=http://host.docker.internal:11434
EG_OLLAMA_MODEL=phi3:mini
```

4. Restart: `docker compose up --build`
5. When chatting, the weaver and verifier will use the LLM instead of stubs.

## Services

| Service | URL | Description |
|---------|-----|-------------|
| API | http://127.0.0.1:8000 | FastAPI backend |
| Qdrant | http://127.0.0.1:6333 | Vector search engine |
| Tika | (internal :9998) | Document parsing (PDF/DOCX/PPTX/HTML) |
| Swagger | http://127.0.0.1:8000/docs | Interactive API docs |

## Phase 4 — Real Multimodal Ingestion + Browser Capture

### What's New

- **Apache Tika** parses PDF, DOCX, PPTX, HTML, and TXT files into extracted text.
- **Tesseract OCR** extracts text from images (PNG, JPG, etc.).
- **faster-whisper** (local) transcribes audio files (WAV, MP3, M4A, etc.).
- **OpenCLIP** generates image embeddings and upserts to Qdrant (`vision` collection).
- **sentence-transformers** (all-MiniLM-L6-v2) generates text embeddings and upserts to Qdrant (`text` collection).
- **Browser capture endpoints** for highlights, bookmarks, research sessions, and visits.
- **EMBEDDING rows** are persisted in SQLite linking memory cards to Qdrant point IDs.

### Setup

```bash
# 1. Copy and configure environment
cp .env.example .env
# Edit .env: set EG_HOST_WATCH_PATH and EG_CAPTURE_API_KEY

# 2. Build and start (includes Tika service)
docker compose up --build
```

> **Note:** First startup will download ML models (~500MB for whisper base + sentence-transformers + OpenCLIP). Models are cached under `./data/models/` and persist across restarts.

> **Lightweight mode:** Set `EG_WHISPER_MODE=stub` and `EG_OPENCLIP_MODE=stub` in `.env` to skip model downloads during development.

### Test 1: PDF Ingestion via Tika

```bash
# Drop a PDF into the watched folder
cp /path/to/sample.pdf ~/echogarden_watch/

# Wait ~5 seconds, then verify:
# 1. Job completed
curl http://127.0.0.1:8000/capture/jobs?limit=1
# 2. Memory card created with extracted text
curl http://127.0.0.1:8000/cards | python3 -m json.tool | head -30
# 3. Check embeddings exist
curl "http://127.0.0.1:8000/cards" | python3 -c "
import json,sys
cards=json.load(sys.stdin)
if cards: print('Memory ID:', cards[0]['memory_id'])
"
```

### Test 2: Image OCR + Vision Embedding

```bash
# Drop a PNG screenshot
cp /path/to/screenshot.png ~/echogarden_watch/

# Wait ~10 seconds, then verify:
curl http://127.0.0.1:8000/cards | python3 -c "
import json, sys
cards = json.load(sys.stdin)
for c in cards:
    meta = json.loads(c.get('metadata','{}')) if isinstance(c.get('metadata'), str) else c.get('metadata',{})
    if meta.get('pipeline') == 'ocr':
        print('OCR Card:', c['memory_id'])
        print('  OCR text:', (meta.get('content_text',''))[:100])
        print('  Vision ref:', meta.get('vision_vector_ref'))
        print('  Text ref:', meta.get('text_vector_ref'))
        break
"

# Confirm 2 EMBEDDING rows (text + vision) via exec trace
curl http://127.0.0.1:8000/capture/jobs?limit=1
```

### Test 3: Audio Transcription

```bash
# Drop an audio file
cp /path/to/recording.wav ~/echogarden_watch/

# Wait ~15 seconds, then verify:
curl http://127.0.0.1:8000/cards | python3 -c "
import json, sys
cards = json.load(sys.stdin)
for c in cards:
    meta = json.loads(c.get('metadata','{}')) if isinstance(c.get('metadata'), str) else c.get('metadata',{})
    if meta.get('pipeline') == 'asr':
        print('ASR Card:', c['memory_id'])
        print('  Transcript:', (meta.get('content_text',''))[:200])
        break
"
```

### Test 4: Browser Highlight Capture

```bash
# POST a highlight (requires API key)
curl -X POST http://127.0.0.1:8000/capture/browser/highlight \
  -H "Content-Type: application/json" \
  -H "X-EG-KEY: changeme-to-a-strong-secret" \
  -d '{
    "url": "https://example.com/article",
    "title": "Example Article",
    "highlight_text": "This is an important highlighted passage from the article.",
    "context": "The surrounding context paragraph."
  }'

# Verify the memory card was created
curl http://127.0.0.1:8000/cards | python3 -c "
import json, sys
cards = json.load(sys.stdin)
for c in cards:
    if c.get('type') == 'browser_highlight':
        print('Highlight Card:', c['memory_id'])
        print('  Summary:', c['summary'][:100])
        break
"
```

### Test 5: Browser Bookmark

```bash
curl -X POST http://127.0.0.1:8000/capture/browser/bookmark \
  -H "Content-Type: application/json" \
  -H "X-EG-KEY: changeme-to-a-strong-secret" \
  -d '{
    "url": "https://example.com/resource",
    "title": "Useful Resource",
    "folder": "Research"
  }'
```

### Test 6: Research Session

```bash
curl -X POST http://127.0.0.1:8000/capture/browser/research_session \
  -H "Content-Type: application/json" \
  -H "X-EG-KEY: changeme-to-a-strong-secret" \
  -d '{
    "session_title": "ML Papers Review",
    "started_ts": "2026-02-14T10:00:00Z",
    "ended_ts": "2026-02-14T11:30:00Z",
    "tabs": [
      {"url": "https://arxiv.org/paper1", "title": "Paper 1"},
      {"url": "https://arxiv.org/paper2", "title": "Paper 2"}
    ],
    "notes": "Reviewed attention mechanisms"
  }'
```

### Browser Capture API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/capture/browser/highlight` | POST | Capture text highlight from a page |
| `/capture/browser/bookmark` | POST | Capture a bookmarked page |
| `/capture/browser/research_session` | POST | Capture a multi-tab research session |
| `/capture/browser/visit` | POST | Capture a page visit (opt-in) |
| `/capture/browser/import_history` | POST | Import browsing history (extension-pushed) |

All browser capture endpoints require the `X-EG-KEY` header matching `EG_CAPTURE_API_KEY`.

### Configuration (Phase 4)

| Env Var | Default | Description |
|---------|---------|-------------|
| `TIKA_URL` | `http://tika:9998` | Apache Tika server URL |
| `EG_MODELS_DIR` | `/data/models` | Model cache directory |
| `EG_WHISPER_MODE` | `local` | `local` or `stub` for ASR |
| `EG_OPENCLIP_MODE` | `local` | `local` or `stub` for vision embeddings |
| `EG_CAPTURE_API_KEY` | (required) | API key for browser capture endpoints |

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
| `/exec/{trace_id}` | GET | Inspect execution trace (nodes + edges) |
| `/tool_calls` | GET | List tool calls (`?trace_id=&limit=50`) |

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
│       ├── orchestrator/
│       │   ├── __init__.py
│       │   ├── models.py
│       │   ├── orchestrator.py
│       │   ├── router.py
│       │   └── llm.py
│       ├── core/
│       │   ├── config.py
│       │   ├── tool_contracts.py
│       │   └── tool_registry.py
│       ├── tools/                     (Phase 4 — real implementations)
│       │   ├── __init__.py
│       │   ├── qdrant_client.py
│       │   ├── doc_parse_impl.py
│       │   ├── ocr_impl.py
│       │   ├── asr_impl.py
│       │   ├── vision_embed_impl.py
│       │   └── text_embed_impl.py
│       ├── db/
│       │   ├── schema.sql
│       │   ├── schema_capture.sql
│       │   ├── schema_phase3.sql
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
│           ├── capture_browser.py     (Phase 4 — browser capture)
│           ├── chat.py
│           ├── exec_trace.py
│           ├── tool_calls.py
│           └── graph.py
├── host_watch/          (default local watch folder)
└── data/                (created at runtime, git-ignored)
    └── models/          (cached ML models)
```

## Phase 6 — Local LLM Enrichment & Disciplined Graph Building

### What changed

- **Summaries are now SHORT** (1-3 sentences, max 400 chars) generated by a local LLM (Phi-3 mini via Ollama). Full text is stored separately in `content_text`.
- **Entity extraction** uses LLM to produce a bounded JSON list of entities (max 30), tags (max 12), and actions (max 10).
- **Graph builder** no longer uses token heuristics. It only creates nodes/edges from extracted entities (~10-30 per doc instead of hundreds).
- **Memory cards** now store `content_text` (full text) and `metadata_json` (structured metadata including entities/tags/actions).
- **DB schema** is auto-migrated at startup to add missing columns (`content_text`, `metadata_json`).
- Everything works **with or without Ollama** — fallback summaries and empty extractions when LLM is unavailable.

### Running Ollama

Install and start Ollama on your host machine:

```bash
# Install Ollama (macOS)
brew install ollama

# Pull the Phi-3 mini model
ollama pull phi3:mini

# Start Ollama server (default port 11434)
ollama serve
```

The API container connects to Ollama via `host.docker.internal:11434` by default.

**Environment variables:**
| Variable | Default | Description |
|---|---|---|
| `EG_OLLAMA_URL` | `http://host.docker.internal:11434` | Ollama server URL |
| `EG_OLLAMA_MODEL` | `phi3:mini` | Model to use for summarization/extraction |

### Testing Phase 6

```bash
# 1. Check LLM status
curl http://127.0.0.1:8000/healthz
# Response includes "llm": "ok" or "llm": "unavailable"

# 2. Check LLM details
curl http://127.0.0.1:8000/debug/llm

# 3. Ingest a PDF and verify enrichment
# (drop a PDF into host_watch/ and wait for processing, or use the API)

# 4. Check last 5 memory cards — summary length, content_text, entities
curl http://127.0.0.1:8000/debug/phase6_summary_stats

# 5. Verify via SQL (inside container):
#    Last 5 cards with summary length:
#    SELECT memory_id, LENGTH(summary) as sum_len, LENGTH(content_text) as ct_len
#    FROM memory_card ORDER BY created_at DESC LIMIT 5;
#
#    Graph nodes per trace:
#    SELECT ge.provenance, COUNT(DISTINCT ge.to_node_id) as node_count
#    FROM graph_edge ge GROUP BY json_extract(ge.provenance, '$.trace_id') LIMIT 10;

# 6. Open the debug dashboard to see Phase 6 fields
open http://127.0.0.1:8000/debug
```

### New Tools (Phase 6)

| Tool | Description |
|---|---|
| `summarizer` | Produces short 1-3 sentence summaries via LLM. Fallback if unavailable. |
| `extractor` | Extracts entities, tags, and actions from text via LLM. Returns empty on failure. |
| `graph_builder` (v0.6) | Builds graph from pre-extracted entities only (no heuristics). |

### Ingestion Pipeline (Phase 6)

**Documents/Text/PDF:**
`doc_parse → summarizer → extractor → text_embed → graph_builder → commit_memory_card`

**Audio:**
`asr → summarizer → extractor → text_embed → graph_builder → commit_memory_card`

**Images:**
`(ocr ∥ vision_embed) → summarizer → extractor → text_embed → graph_builder → commit_memory_card`

## Phase 7 — Grounded Q&A (Weaver + Verifier)

Phase 7 adds a full **retrieval → weave → verify** chat pipeline that produces
grounded answers with citations and a verification verdict.

### POST /chat

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is EchoGarden?",
    "top_k": 8,
    "use_graph": true,
    "hops": 1
  }'
```

**Response shape:**

```json
{
  "trace_id": "...",
  "answer": "...",
  "verdict": "pass|revise|abstain",
  "citations": [
    {"memory_id": "...", "quote": "...", "source_type": "...", "created_at": "..."}
  ],
  "evidence": [
    {"memory_id": "...", "summary": "...", "snippet": "...", "score": 0.0, "reasons": [...]}
  ],
  "steps": [...],
  "status": "ok"
}
```

### How it works

1. **Retrieval** — Phase 5 hybrid search (FTS + semantic + graph expand + recency).
2. **Weaver** — Produces an answer grounded ONLY in retrieved evidence.
   - LLM mode: strict system prompt + JSON output with inline citations.
   - Stub mode: bullet list of top memory summaries.
3. **Verifier** — Checks that every claim is supported by evidence.
   - LLM mode: flags unsupported claims, can revise or abstain.
   - Heuristic mode: checks for citation presence.
4. **Persist** — Saves `conversation_turn` (with verdict) + `chat_citation` rows.
5. **Trace** — Full execution graph: retrieval → weaver → verifier.

### Verdicts

| Verdict | Meaning |
|---------|---------|
| `pass`    | All claims supported by evidence |
| `revise`  | Some unsupported claims removed; revised answer returned |
| `abstain` | Core answer unsupported; explanation returned instead |

### Testing Phase 7

```bash
# 1. Ingest some content first
curl -X POST http://127.0.0.1:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"text": "EchoGarden is a local-first personal knowledge garden."}'

# 2. Chat about it
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is EchoGarden?"}'

# 3. Verify trace shows retrieval → weaver → verifier
# (use trace_id from chat response)
curl http://127.0.0.1:8000/exec/<trace_id>

# 4. Test abstain with unknown topic
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the capital of Mars?"}'
```

### Database (Phase 7)

New/updated tables:

- **conversation_turn** — added `verdict TEXT` column
- **chat_citation** — `citation_id`, `turn_id`, `memory_id`, `quote`, `span_start`, `span_end`, `created_at`

---

## Phase 8 — Search-first Knowledge OS UI

Phase 8 adds a local web UI (Vite + React + TypeScript + Tailwind) with four surfaces, plus new backend endpoints.

### Quick Start

```bash
# Start everything (API + UI + dependencies)
docker compose up --build

# UI opens at:
open http://127.0.0.1:5173

# API docs still at:
open http://127.0.0.1:8000/docs
```

### Workflow

1. **Drop a file** — use the existing ingest endpoint or file watcher
2. **Home** — see your Daily Digest at `http://127.0.0.1:5173/`
3. **Search** — go to `/search`, type a query → see ranked results with FTS/semantic/graph badges
4. **Ask** — go to `/ask`, ask a question → get a grounded answer with citations + evidence
5. **Graph** — go to `/graph`, search for nodes or click "Explore in Graph" from any card

### UI Pages

| Page | Route | Description |
|------|-------|-------------|
| Home | `/` | Daily Digest — recent cards, top entities, actions, clusters |
| Search | `/search` | Hybrid search with score + reason badges, card preview |
| Ask | `/ask` | Grounded Q&A with citations, evidence list, trace link, graph |
| Graph | `/graph` | 2D/3D graph explorer with expand, filter, search |

### New Backend Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/cards?limit=50&offset=0&source_type=&card_type=&q=` | List/filter/search cards |
| GET | `/cards/{memory_id}` | Get single card detail |
| GET | `/digest?window=24h\|7d\|30d&limit=50` | Daily digest payload |
| GET | `/graph/subgraph?seed=<node_id>&hops=1\|2&limit=200` | Subgraph for visualization |
| GET | `/graph/search?query=<text>&type=<optional>&limit=20` | Search graph nodes by name |
| GET | `/graph/neighbors?node_id=<node_id>&hops=1\|2&limit=200` | Node neighbors |

### Local UI Development (without Docker)

```bash
cd ui
npm install
npm run dev
# Proxies /api → http://localhost:8000
```
