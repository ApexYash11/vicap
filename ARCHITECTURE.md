# VICAP Studio — Backend Architecture Plan

## Tech Stack

| Component | Choice | Purpose |
|-----------|--------|---------|
| **Framework** | FastAPI (Python 3.12) | Async API server |
| **Database** | PostgreSQL + SQLAlchemy (async) + Alembic | Persistent session storage, API key management, job tracking |
| **Job Queue** | arq (Redis-backed) | Background processing for long videos |
| **LLM** | Fireworks API (Kimi K2.5 + MiniMax M2.7) | Perception & caption compilation |
| **Cache/Session** | Redis | Live session state during processing, job queue broker |
| **Auth** | API Key (`X-API-Key` header, SHA256 hashed) | Simple key-based access control |
| **API Versioning** | `/api/v1/` prefix | Future-proof routing |
| **Media** | ffmpeg | Video/audio normalization, chunking, frame diff |
| **Storage** | LocalFileStore (abstract FileStore protocol) | Upload/output file management |

---

## Project Structure

```
src/vicap/
├── __init__.py
├── cli.py                    # CLI entrypoint (batch, stream, clips)
├── config.py                 # Pydantic Settings + YAML config loaders
├── pipeline.py               # Orchestrator — ingest → perceive → compile → assist → store
│
├── api/
│   ├── __init__.py
│   ├── main.py               # FastAPI app, CORS, exception handlers, lifecycle
│   └── v1/
│       ├── __init__.py
│       ├── router.py         # Aggregates all v1 routers under /api/v1/
│       ├── health.py         # GET  /api/v1/health
│       ├── sessions.py       # POST batch/stream, GET/{id}, POST/{id}/ask, DELETE/{id}
│       ├── jobs.py           # GET list, GET/{id}, POST/{id}/cancel
│       └── clips.py          # GET list, POST/{name}/batch
│
├── core/                     # Cross-cutting infrastructure
│   ├── __init__.py
│   ├── auth.py               # API key validation dependency (X-API-Key → SHA256 → DB)
│   ├── db.py                 # SQLAlchemy async engine + session factory + Base + lifecycle
│   ├── exceptions.py         # Unified error response schema + global handlers
│   ├── filestore.py          # FileStore ABC + LocalFileStore implementation
│   └── security.py           # Key hashing utility
│
├── models/
│   ├── __init__.py           # Re-exports domain models (backward-compatible imports)
│   ├── domain.py             # SessionMemory, SceneIR, TranscriptSegment, etc.
│   ├── sql.py                # SQLAlchemy ORM models: ApiKey, Session, Job
│   └── schemas.py            # Pydantic request/response schemas for all endpoints
│
├── domain/                   # Business logic layer (stub — ready for Phase 2-3)
│   ├── __init__.py
│   ├── session_service.py
│   ├── job_service.py
│   └── api_key_service.py
│
├── ingest/
│   └── video.py              # ffmpeg wrapper: normalize, chunk, frame diff, encode b64
├── perceive/
│   └── worker.py             # Kimi K2.5 → Scene IR + transcript
├── compile/
│   └── worker.py             # MiniMax M2.7 → Persona Council → 4 caption styles
├── assistant/
│   └── worker.py             # MiniMax M2.7 → summary, action items, Q&A/plan/model/debug
├── fireworks/
│   └── client.py             # HTTP client for Fireworks API + UsageLedger + retry logic
├── session/
│   ├── __init__.py
│   └── store.py              # Redis-backed SessionStore for live/in-flight state
│
└── worker/
    ├── __init__.py
    └── arq_worker.py         # arq WorkerSettings + process_video_job function

alembic/
├── alembic.ini
├── env.py                    # Async-aware Alembic environment
├── script.py.mako
└── versions/
    └── 0001_initial.py       # Creates api_keys, sessions, jobs tables
```

---

## Layer Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   CLIENT LAYER                              │
│  CLI (argparse)    │   Demo UI (HTML/JS)   │    External    │
├─────────────────────────────────────────────────────────────┤
│                    API GATEWAY (FastAPI)                    │
│  Middleware: CORS · Auth (X-API-Key) · Exception handlers  │
│  Routers: /api/v1/{health, sessions, jobs, clips}          │
├─────────────────────────────────────────────────────────────┤
│                  ORCHESTRATION LAYER                        │
│  Pipeline (coordinator) │ arq Background Worker (Redis)     │
├─────────────────────────────────┬───────────────────────────┤
│  CORE DOMAIN LAYER              │   INFRASTRUCTURE LAYER     │
│                                 │                            │
│  IngestService                  │  FireworksClient (LLM)     │
│   ├─ normalize_media            │  SessionStore (Redis)      │
│   ├─ chunk_video                │  PostgreSQL (SQLAlchemy)   │
│   └─ frame_diff                 │  FileStore (local)         │
│                                 │  Config (Settings/YAML)    │
│  PerceiveWorker                 │  UsageLedger               │
│   └─ Kimi K2.5 → Scene IR      │                            │
│                                 │                            │
│  CompileWorker                  │                            │
│   └─ MiniMax M2.7 → Captions   │                            │
│                                 │                            │
│  AssistantWorker                │                            │
│   ├─ Rolling Summary            │                            │
│   ├─ Action Items               │                            │
│   └─ Multi-mode QA              │                            │
└─────────────────────────────────┴────────────────────────────┘
```

---

## Database Schema (PostgreSQL)

### api_keys

| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK, default gen_random_uuid() |
| key_hash | VARCHAR(64) | UNIQUE, NOT NULL, indexed |
| name | VARCHAR(255) | NOT NULL |
| is_active | BOOLEAN | NOT NULL, default true |
| rate_limit | INTEGER | NOT NULL, default 100 |
| created_at | TIMESTAMPTZ | NOT NULL, default now() |
| last_used_at | TIMESTAMPTZ | nullable |

### sessions

| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK, default gen_random_uuid() |
| mode | VARCHAR(20) | NOT NULL, default 'media' |
| source_path | TEXT | nullable |
| source_filename | VARCHAR(255) | nullable |
| status | VARCHAR(20) | NOT NULL, default 'created', indexed |
| error_message | TEXT | nullable |
| chunk_count | INTEGER | default 0 |
| rolling_summary | TEXT | nullable |
| captions_data | JSONB | nullable |
| scenes_data | JSONB | nullable |
| transcripts_data | JSONB | nullable |
| action_items | JSONB | nullable |
| qa_history | JSONB | nullable |
| ledger_data | JSONB | nullable |
| api_key_id | UUID | FK → api_keys.id (SET NULL on delete) |
| created_at | TIMESTAMPTZ | NOT NULL, default now() |
| updated_at | TIMESTAMPTZ | NOT NULL, default now(), on update now() |

### jobs

| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK, default gen_random_uuid() |
| session_id | UUID | FK → sessions.id (CASCADE on delete), NOT NULL |
| job_type | VARCHAR(20) | NOT NULL, default 'batch' |
| status | VARCHAR(20) | NOT NULL, default 'queued', indexed |
| progress | JSONB | default '{}' |
| error_message | TEXT | nullable |
| queued_at | TIMESTAMPTZ | NOT NULL, default now() |
| started_at | TIMESTAMPTZ | nullable |
| completed_at | TIMESTAMPTZ | nullable |

---

## Data Model (Entity Relationship)

```
Session
├── id: UUID (PK)
├── mode: media | conference
├── source_path: str
├── source_filename: str
├── status: created | processing | completed | failed
├── error_message: str?
├── chunk_count: int
├── rolling_summary: text
├── captions_data: JSONB          ← captions_by_style dict
├── scenes_data: JSONB            ← array of SceneIR
├── transcripts_data: JSONB       ← array of TranscriptSegment
├── action_items: JSONB
├── qa_history: JSONB
├── ledger_data: JSONB            ← UsageLedger snapshot
├── api_key_id: UUID → api_keys
├── created_at: timestamptz
└── updated_at: timestamptz

ApiKey
├── id: UUID (PK)
├── key_hash: text (UNIQUE)       ← SHA256 of raw key
├── name: text
├── is_active: boolean
├── rate_limit: int (req/min)
├── created_at: timestamptz
└── last_used_at: timestamptz

Job
├── id: UUID (PK)
├── session_id: UUID → sessions
├── job_type: batch | stream
├── status: queued | running | completed | failed | cancelled
├── progress: JSONB               ← {chunks_done, chunks_total}
├── error_message: text?
├── queued_at: timestamptz
├── started_at: timestamptz?
└── completed_at: timestamptz?
```

---

## API Surface (`/api/v1/`)

### System

| Method | Endpoint | Description | Status |
|--------|----------|-------------|--------|
| `GET` | `/health` | Health check + API key status + DB connection | ✅ |

### Sessions

| Method | Endpoint | Description | Status |
|--------|----------|-------------|--------|
| `POST` | `/sessions` | Upload + async job creation (returns `job_id`) | ❌ Phase 2 |
| `POST` | `/sessions/batch` | Upload + synchronous batch process | ✅ |
| `POST` | `/sessions/stream` | Upload + SSE live stream | ✅ |
| `GET` | `/sessions` | List sessions (paginated, filterable by status) | ❌ Phase 3 |
| `GET` | `/sessions/{id}` | Get full session state | ✅ |
| `DELETE` | `/sessions/{id}` | Delete session + artifacts | ✅ |
| `POST` | `/sessions/{id}/reprocess` | Re-run pipeline on existing session | ❌ Phase 2 |
| `POST` | `/sessions/{id}/ask` | Q&A / plan / model / debug | ✅ |

### Jobs

| Method | Endpoint | Description | Status |
|--------|----------|-------------|--------|
| `GET` | `/jobs` | List jobs (paginated) | ✅ |
| `POST` | `/jobs` | Create a processing job (alt to sessions POST) | ❌ Phase 2 |
| `GET` | `/jobs/{id}` | Poll job status + progress | ✅ |
| `POST` | `/jobs/{id}/cancel` | Cancel queued/running job | ✅ |

### Clips

| Method | Endpoint | Description | Status |
|--------|----------|-------------|--------|
| `GET` | `/clips` | List pre-loaded clips from `data/clips/` | ✅ |
| `POST` | `/clips/{name}/batch` | Process a pre-loaded clip | ✅ |

### Admin

| Method | Endpoint | Description | Status |
|--------|----------|-------------|--------|
| `GET` | `/admin/usage` | API usage stats (token counts, call counts) | ❌ Phase 4 |

---

## Request/Response Schemas

### POST /sessions/batch

```
Request: multipart/form-data
  file: <binary>
  mode: "media" | "conference"  (optional, default media)

Response 200:
{
  "session_id": "uuid",
  "captions": { "formal": [...], "sarcastic": [...], ... },
  "summary": "...",
  "action_items": [...],
  "ledger": { "kimi_calls": 3, "minimax_calls": 3, "total_calls": 6 }
}
```

### POST /sessions (async — Phase 2)

```
Request: multipart/form-data
  file: <binary>
  mode: "media" | "conference"

Response 202:
{
  "session_id": "uuid",
  "job_id": "uuid",
  "status": "queued",
  "poll_url": "/api/v1/jobs/{job_id}"
}
```

### POST /sessions/stream

```
SSE Event Stream:

event: session_start
data: {"event":"session_start","session_id":"uuid"}

event: transcript
data: {"event":"transcript","chunk_id":0,"segments":[...],"scene":"compact IR","skipped_perception":false}

event: captions
data: {"event":"captions","chunk_id":0,"captions":{"formal":"...","sarcastic":"..."}}

event: session_complete
data: {"event":"session_complete","session_id":"uuid","summary":"...","action_items":[...],"ledger":{...}}
```

### GET /sessions/{id}

```
Response 200:
{
  "session_id": "uuid",
  "mode": "media",
  "source_path": "data/clips/demo.mp4",
  "created_at": "2026-07-06T12:00:00Z",
  "status": "completed",
  "progress": { "chunks_done": 5, "chunks_total": 5 },
  "captions_by_style": {
    "formal": ["caption1", "caption2"],
    "sarcastic": ["..."],
    "humorous_tech": ["..."],
    "humorous_non_tech": ["..."]
  },
  "scenes": [...],
  "transcripts": [...],
  "rolling_summary": "Meeting discussed...",
  "action_items": [{"task":"Fix bug","owner":"Alice"}],
  "qa_history": [...],
  "ledger": {"kimi_calls":3,"minimax_calls":3,"total_calls":6}
}
```

### GET /jobs/{id}

```
Response 200:
{
  "job_id": "uuid",
  "session_id": "uuid",
  "job_type": "batch",
  "status": "running",               // queued | running | completed | failed | cancelled
  "progress": { "chunks_done": 3, "chunks_total": 8 },
  "error_message": null,
  "queued_at": "2026-07-06T12:00:00Z",
  "started_at": "2026-07-06T12:00:01Z",
  "completed_at": null
}
```

---

## Backend Flow (Data Pipeline)

```
┌──────────┐    ┌─────────┐    ┌──────────┐    ┌───────────┐    ┌────────────┐
│  CLIENT  │───▶│  API    │───▶│ PIPELINE │───▶│   STORE   │───▶│  RESPONSE  │
│ Upload   │    │ FastAPI │    │  (async) │    │  Redis    │    │ (JSON/SSE) │
└──────────┘    └─────────┘    └──────────┘    └───────────┘    └────────────┘
                     │               │
                     │         ┌─────┴──────┐
                     │         │  arq JOBS  │  (Phase 2)
                     │         │  Worker    │
                     │         └─────┬──────┘
                     │               │
                ┌────┴────┐         │
                │  FILES  │         │
                │  Store  │         │
                └─────────┘         │
                                    ▼
                       ┌────────────────────────┐
                       │   INGEST (ffmpeg)       │
                       │  normalize → chunk      │
                       │  frame_diff → is_static │
                       │  encode_b64             │
                       └───────────┬────────────┘
                                   │ (per chunk)
                                   ▼
                       ┌────────────────────────┐
                       │  PERCEIVE (Kimi K2.5)   │
                       │  Scene IR + transcript  │
                       └───────────┬────────────┘
                                   │
                                   ▼
                       ┌────────────────────────┐
                       │  COMPILE (MiniMax M2.7) │
                       │  Persona Council        │
                       │  → 4 caption styles     │
                       └───────────┬────────────┘
                                   │
                                   ▼
                       ┌────────────────────────┐
                       │  ASSIST (MiniMax M2.7)  │
                       │  summary + action items │
                       └───────────┬────────────┘
                                   │
                                   ▼
                       ┌────────────────────────┐
                       │  SESSION STORE          │
                       │  Redis (live)           │
                       │  PostgreSQL (source of  │
                       │    truth on completion) │
                       │  JSON export to outputs │
                       └────────────────────────┘
```

---

## Per-Chunk Processing Flow

```
┌────────────────────────────────────────────────────────┐
│                    CHUNK PROCESSING                     │
│                                                        │
│  1. chunk_video (ffmpeg)                               │
│     ├─ 3s duration, 1s overlap                         │
│     ├─ 1fps, 360p, libx264                             │
│     └─ frame_diff_ratio < 0.08 → static skip           │
│                                                        │
│  2. PerceiveWorker (Kimi K2.5)                         │
│     ├─ Input: base64 video chunk                       │
│     ├─ Output: {entities, actions, mood,               │
│     │   tech_signals, delivery,                        │
│     │   dialogue_summary, confidence,                  │
│     │   transcript: [{start, end, text, speaker}]}     │
│     └─ Writes SceneIR + TranscriptSegment objects      │
│                                                        │
│  3. CompileWorker (MiniMax M2.7)                       │
│     ├─ Input: SceneIR + TranscriptSegments             │
│     ├─ Persona Council prompt                          │
│     ├─ Output: {"formal":"...", "sarcastic":"...",     │
│     │   "humorous_tech":"...",                          │
│     │   "humorous_non_tech":"..."}                     │
│     ├─ Delta mode: passes prior captions for appending │
│     └─ Validate: entity-gate anti-hallucination check  │
│                                                        │
│  4. Session Memory update                              │
│     ├─ Append scene, transcripts, captions             │
│     └─ Save to Redis                                   │
│                                                        │
│  == CHUNK LOOP END ==                                  │
│                                                        │
│  5. AssistantWorker (MiniMax M2.7)                     │
│     ├─ Rolling summary (3-5 sentences)                 │
│     └─ Action items (JSON array)                       │
│                                                        │
│  6. Store + Export                                     │
│     ├─ Final save to Redis                             │
│     ├─ Save to PostgreSQL (on completion)              │
│     └─ Write JSON to outputs/{session_id}_captions.json│
└────────────────────────────────────────────────────────┘
```

---

## Auth Flow (API Key)

```
Request → FastAPI dependency injection
           │
           ▼
   Extract X-API-Key header
           │
           ▼
   SHA256 hash → SELECT * FROM api_keys
                  WHERE key_hash = <hash>
                    AND is_active = true
           │
           ▼
   Valid + active? ──No──→ 403 Forbidden (AppException)
           │
          Yes
           │
           ▼
   UPDATE api_keys SET last_used_at = now()
   Attach api_key_id (UUID) to request state
           │
           ▼
      → Route handler
```

---

## Async Job Flow (arq — Phase 2)

```
POST /api/v1/sessions
  ├── Validate API key
  ├── Save uploaded file to data/uploads/
  ├── Create Session record in PostgreSQL (status=created)
  ├── Create Job record in PostgreSQL (status=queued)
  ├── Enqueue arq job: {session_id, job_id, file_path}
  └── Return 202: {session_id, job_id, status: "queued"}

─── arq Worker (separate process) ────

arq_worker.py:
  async def process_video_job(ctx, session_id, job_id, file_path):
      1. Update job status → running
      2. Update session status → processing
      3. Run pipeline.process_batch()
         - Per chunk: update job.progress {chunks_done, chunks_total}
         - On error: job.status = failed, set error_message
      4. Persist session final data to PostgreSQL
      5. Update job status → completed
      6. Update session status → completed

─── Client Polling ────

Client: GET /api/v1/jobs/{job_id}
  ├── Returns: {job_id, status, progress, session_id, ...}
  └── On status=completed → GET /api/v1/sessions/{session_id} for result
```

---

## Docker Compose

```yaml
services:
  api:
    build: .
    ports: ["8000:8000"]
    env_file: .env
    volumes:
      - ./data:/app/data
      - ./outputs:/app/outputs
    depends_on: [redis, db]
    command: uvicorn vicap.api.main:app --host 0.0.0.0 --port 8000

  worker:
    build: .
    env_file: .env
    volumes:
      - ./data:/app/data
      - ./outputs:/app/outputs
    depends_on: [redis, db]
    command: python -m vicap.worker.arq_worker

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: vicap
      POSTGRES_USER: vicap
      POSTGRES_PASSWORD: vicap_secret
    ports: ["5432:5432"]
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

---

## Environment Variables (`.env`)

```bash
# Fireworks AI
FIREWORKS_API_KEY=your_fireworks_api_key
FIREWORKS_BASE_URL=https://api.fireworks.ai/inference/v1
KIMI_MODEL=accounts/fireworks/models/kimi-k2p5
MINIMAX_MODEL=accounts/fireworks/models/minimax-m2p7

# Database
DATABASE_URL=postgresql+asyncpg://vicap:vicap_secret@db:5432/vicap

# Redis
REDIS_URL=redis://redis:6379/0
REDIS_JOBS_URL=redis://redis:6379/1

# Auth
API_KEY_REQUIRED=true
RATE_LIMIT_PER_MINUTE=100

# Media processing
CHUNK_DURATION_SEC=3.0
CHUNK_OVERLAP_SEC=1.0
MOTION_GATE_THRESHOLD=0.08
SUMMARY_INTERVAL_SEC=30

# Paths
VICAP_DATA_DIR=./data
VICAP_OUTPUT_DIR=./outputs
```

---

## Implementation Status

| Phase | Scope | Status | Key Deliverables |
|-------|-------|--------|------------------|
| **Phase 1** | DB + Auth + API versioning | ✅ **Done** | SQLAlchemy ORM models (ApiKey, Session, Job), Alembic migration, API key auth dependency, `/api/v1/` router structure, Docker Compose with PostgreSQL, config updates, v1 routers for health/sessions/jobs/clips, FileStore ABC + LocalFileStore, arq worker skeleton, unified exception handlers, Pydantic schemas |

---

## What's Still Left

### Phase 2 — Async Job Queue (arq)

| Item | What | Why |
|------|------|-----|
| 2.1 | Wire `POST /sessions` to create arq job instead of blocking | Long videos shouldn't hold HTTP request open |
| 2.2 | Complete `arq_worker.py` — add DB writes for session + job status | Worker skeleton exists but needs full implementation |
| 2.3 | Add `POST /sessions/{id}/reprocess` endpoint | Allow re-running pipeline on existing session |
| 2.4 | Add job progress reporting from Pipeline to arq | Per-chunk progress updates during processing |
| 2.5 | File cleanup on job completion | Remove temp uploads after processing |

### Phase 3 — Session Persistence in PostgreSQL

| Item | What | Why |
|------|------|-----|
| 3.1 | Create `SessionService` that writes session data to PostgreSQL on completion | Redis is ephemeral; Postgres is source of truth |
| 3.2 | Add `GET /sessions` with pagination + status filtering | List all sessions for dashboard |
| 3.3 | Add session TTL / archival logic | Don't let Postgres fill up with stale sessions |
| 3.4 | Sync protocol: Redis → Postgres on chunk completion + final save | Consistent state across stores |

### Phase 4 — Polish

| Item | What | Why |
|------|------|-----|
| 4.1 | Rate limiting middleware (per-key via `slowapi`) | Currently no limit enforcement |
| 4.2 | Structured JSON logging with `structlog` + request-id tracing | Debuggability across distributed services |
| 4.3 | Prometheus metrics endpoint (`/metrics`) | Call counts, latency histograms, error rates, token usage |
| 4.4 | Admin usage endpoint (`GET /admin/usage`) | Aggregate ledger across all sessions for an API key |
| 4.5 | API key management CLI command (`vicap keys create`) | Bootstrap API keys without raw SQL |
| 4.6 | S3/GCS FileStore implementation | Production cloud storage support |
| 4.7 | Health endpoint improvements | Return more granular component status |
| 4.8 | SSE cap for long-running streams | Route sessions > 60s through async job queue instead |
| 4.9 | Enhanced OpenAPI examples | Better auto-generated API docs |

### Backlog / Future

| Item | What |
|------|------|
| 5.1 | User model + JWT auth (beyond API keys) |
| 5.2 | Export formats: SRT, VTT, TXT, CSV |
| 5.3 | Webhook callback on job completion (vs polling) |
| 5.4 | Cache Scene IR for near-identical chunks |
| 5.5 | Cross-session memory for AssistantWorker |
| 5.6 | Human-in-the-loop: caption correction → few-shot feedback |
