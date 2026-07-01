# VICAP Studio

**Caption Compiler + Real-Time Meeting Assistant** for videos and conference calls.

Built for the AMD Developer Hackathon Track 2 (Fireworks AI only) using **Kimi K2.5** (perceive) + **MiniMax M2.7** (compile + assist).

## Architecture

```
Video / Conference audio
        ↓
   Kimi K2.5 → Scene IR + transcript
        ↓
   Session Memory (Redis)
        ↓
   MiniMax M2.7 → 4 caption styles (Persona Council)
                 → summary, Q&A, plan/model/debug
```

## Quick start

```bash
cp .env.example .env
# Set FIREWORKS_API_KEY and optional KIMI_MODEL deployment suffix

pip install -e ".[dev]"

# Run API + demo UI
uvicorn vicap.api.main:app --reload

# Batch process a clip
vicap batch path/to/clip.mp4

# Process all hackathon clips
vicap clips
```

## Docker

```bash
docker compose up --build
```

Open http://localhost:8000 for Director's Room UI.

## API

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `POST /sessions/batch` | Batch process upload |
| `POST /sessions/stream` | SSE live stream |
| `GET /sessions/{id}` | Get session state |
| `POST /sessions/{id}/ask` | Q&A / plan / model / debug |
| `POST /clips/{name}/batch` | Process clip from `data/clips/` |

## Hackathon Track 2

Place fixed clips in `data/clips/` and run:

```bash
vicap clips --output-dir outputs/
```

Exports 4 styles per clip: formal, sarcastic, humorous-tech, humorous-non-tech.

## Tech stack

Python 3.12 · FastAPI · ffmpeg · Redis · Fireworks API · Docker · HTML/JS demo
