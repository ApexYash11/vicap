from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from vicap.config import ROOT, get_settings
from vicap.models import SessionMode
from vicap.pipeline import Pipeline
from vicap.session.store import SessionStore

logger = logging.getLogger(__name__)

app = FastAPI(
    title="VICAP Studio",
    description="Caption compiler + real-time meeting assistant",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

pipeline = Pipeline(store=SessionStore(get_settings().redis_url))
DEMO_DIR = ROOT / "demo"


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    mode: str = Field(default="qa", pattern="^(qa|plan|model|debug)$")


@app.get("/health")
async def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "has_api_key": settings.has_api_key,
        "kimi_model": settings.kimi_model,
        "minimax_model": settings.minimax_model,
    }


@app.post("/sessions/batch")
async def batch_process(
    file: UploadFile = File(...),
    mode: SessionMode = Query(default=SessionMode.MEDIA),
) -> dict:
    settings = get_settings()
    if not settings.has_api_key:
        raise HTTPException(503, "FIREWORKS_API_KEY not configured")

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    upload_path = settings.data_dir / "clips" / file.filename
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    upload_path.write_bytes(await file.read())

    memory = await pipeline.process_batch(upload_path, mode=mode)
    return {
        "session_id": memory.session_id,
        "captions": memory.captions_by_style,
        "summary": memory.rolling_summary,
        "action_items": [a.to_dict() for a in memory.action_items],
        "ledger": pipeline.client.ledger.to_dict(),
    }


@app.post("/sessions/stream")
async def stream_process(
    file: UploadFile = File(...),
    mode: SessionMode = Query(default=SessionMode.MEDIA),
):
    settings = get_settings()
    if not settings.has_api_key:
        raise HTTPException(503, "FIREWORKS_API_KEY not configured")

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    upload_path = settings.data_dir / "clips" / file.filename
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    upload_path.write_bytes(await file.read())

    async def event_generator():
        async for event in pipeline.stream_session(upload_path, mode=mode):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict:
    memory = await pipeline.store.get(session_id)
    if not memory:
        raise HTTPException(404, "Session not found")
    return memory.to_dict()


@app.post("/sessions/{session_id}/ask")
async def ask_session(session_id: str, body: AskRequest) -> dict:
    settings = get_settings()
    if not settings.has_api_key:
        raise HTTPException(503, "FIREWORKS_API_KEY not configured")
    try:
        return await pipeline.ask_session(session_id, body.question, body.mode)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/clips/{clip_name}/batch")
async def batch_named_clip(clip_name: str) -> dict:
    """Process a clip from data/clips/ (hackathon fixed clip set)."""
    settings = get_settings()
    if not settings.has_api_key:
        raise HTTPException(503, "FIREWORKS_API_KEY not configured")

    clip_path = settings.clips_dir / clip_name
    if not clip_path.exists():
        raise HTTPException(404, f"Clip not found: {clip_name}")

    memory = await pipeline.process_batch(clip_path)
    return {
        "session_id": memory.session_id,
        "clip": clip_name,
        "captions": memory.captions_by_style,
        "summary": memory.rolling_summary,
        "ledger": pipeline.client.ledger.to_dict(),
    }


@app.get("/clips")
async def list_clips() -> dict:
    settings = get_settings()
    clips_dir = settings.clips_dir
    clips_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(p.name for p in clips_dir.iterdir() if p.is_file())
    return {"clips": files}


if DEMO_DIR.exists():
    app.mount("/demo", StaticFiles(directory=str(DEMO_DIR), html=True), name="demo")

    @app.get("/")
    async def root():
        return FileResponse(DEMO_DIR / "index.html")
