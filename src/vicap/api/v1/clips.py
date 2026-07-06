from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from vicap.config import get_settings
from vicap.core.auth import get_api_key_id
from vicap.models.schemas import BatchProcessResponse, ClipListResponse
from vicap.pipeline import Pipeline

logger = logging.getLogger(__name__)
router = APIRouter(tags=["clips"])

pipeline = Pipeline()


@router.get("/clips", response_model=ClipListResponse)
async def list_clips() -> ClipListResponse:
    settings = get_settings()
    clips_dir = settings.clips_dir
    clips_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(p.name for p in clips_dir.iterdir() if p.is_file())
    return ClipListResponse(clips=files)


@router.post("/clips/{clip_name}/batch", response_model=BatchProcessResponse)
async def batch_named_clip(
    clip_name: str,
    api_key_id: str = Depends(get_api_key_id),
) -> BatchProcessResponse:
    settings = get_settings()
    if not settings.has_api_key:
        raise HTTPException(503, "FIREWORKS_API_KEY not configured")

    clip_path = settings.clips_dir / clip_name
    if not clip_path.exists():
        raise HTTPException(404, f"Clip not found: {clip_name}")

    memory = await pipeline.process_batch(clip_path)
    return BatchProcessResponse(
        session_id=memory.session_id,
        captions=memory.captions_by_style,
        summary=memory.rolling_summary,
        action_items=[a.to_dict() for a in memory.action_items],
        ledger=pipeline.client.ledger.to_dict(),
    )
