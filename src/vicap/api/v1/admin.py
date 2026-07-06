from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from vicap.core.auth import get_api_key_id
from vicap.core.db import get_session
from vicap.domain.api_key_service import ApiKeyService
from vicap.fireworks.client import FireworksClient

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin"])


@router.get("/admin/usage")
async def get_usage(
    api_key_id: str = Depends(get_api_key_id),
    db: AsyncSession = Depends(get_session),
) -> dict:
    key_svc = ApiKeyService(db)
    key_stats = await key_svc.get_usage_stats()

    client = FireworksClient()
    ledger = client.ledger.to_dict()

    return {
        "api_keys": key_stats,
        "current_session_ledger": ledger,
    }
