from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from vicap.config import get_settings
from vicap.core.db import get_session
from vicap.models.schemas import HealthResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health(db: AsyncSession = Depends(get_session)) -> HealthResponse:
    settings = get_settings()
    db_ok = False
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    return HealthResponse(
        status="ok",
        has_api_key=settings.has_api_key,
        kimi_model=settings.kimi_model,
        minimax_model=settings.minimax_model,
        db_connected=db_ok,
    )
