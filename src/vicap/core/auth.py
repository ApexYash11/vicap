from __future__ import annotations

import hashlib
import secrets
import logging

from fastapi import Header, HTTPException, Request, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vicap.core.db import get_session
from vicap.models.sql import ApiKey as ApiKeyModel

logger = logging.getLogger(__name__)


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def generate_api_key() -> tuple[str, str]:
    raw = f"vicap_{secrets.token_hex(32)}"
    return raw, hash_api_key(raw)


async def get_api_key_id(
    x_api_key: str = Header(default="", alias="X-API-Key"),
    session: AsyncSession = Depends(get_session),
) -> str:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    key_hash = hash_api_key(x_api_key)
    result = await session.execute(
        select(ApiKeyModel).where(
            ApiKeyModel.key_hash == key_hash,
            ApiKeyModel.is_active == True,
        )
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=403, detail="Invalid or inactive API key")

    api_key.last_used_at = __import__("datetime").datetime.utcnow()
    await session.commit()

    return str(api_key.id)
