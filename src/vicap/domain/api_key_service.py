from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from vicap.core.security import hash_api_key
from vicap.core.auth import generate_api_key
from vicap.models.sql import ApiKey as ApiKeyModel

logger = logging.getLogger(__name__)


class ApiKeyService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_key(self, name: str, rate_limit: int = 100) -> tuple[str, ApiKeyModel]:
        raw_key, key_hash = generate_api_key()
        api_key = ApiKeyModel(
            key_hash=key_hash,
            name=name,
            rate_limit=rate_limit,
        )
        self.db.add(api_key)
        await self.db.commit()
        await self.db.refresh(api_key)
        return raw_key, api_key

    async def get_key(self, key_id: str) -> ApiKeyModel | None:
        try:
            kid = UUID(key_id)
        except ValueError:
            return None
        result = await self.db.execute(select(ApiKeyModel).where(ApiKeyModel.id == kid))
        return result.scalar_one_or_none()

    async def list_keys(self) -> list[ApiKeyModel]:
        result = await self.db.execute(select(ApiKeyModel).order_by(ApiKeyModel.created_at.desc()))
        return list(result.scalars().all())

    async def revoke_key(self, key_id: str) -> bool:
        try:
            kid = UUID(key_id)
        except ValueError:
            return False
        result = await self.db.execute(select(ApiKeyModel).where(ApiKeyModel.id == kid))
        key = result.scalar_one_or_none()
        if not key:
            return False
        key.is_active = False
        await self.db.commit()
        return True

    async def get_usage_stats(self) -> dict:
        total_keys = await self.db.execute(select(func.count(ApiKeyModel.id)))
        active_keys = await self.db.execute(
            select(func.count(ApiKeyModel.id)).where(ApiKeyModel.is_active == True)
        )
        return {
            "total_keys": total_keys.scalar() or 0,
            "active_keys": active_keys.scalar() or 0,
        }
