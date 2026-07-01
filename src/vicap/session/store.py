from __future__ import annotations

import json
from typing import Any

from vicap.models import SessionMemory


class SessionStore:
    """In-memory session store with optional Redis backing."""

    def __init__(self, redis_url: str | None = None) -> None:
        self._memory: dict[str, SessionMemory] = {}
        self._redis = None
        self._redis_url = redis_url

    async def _get_redis(self):
        if self._redis is None and self._redis_url:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
                await self._redis.ping()
            except Exception:
                self._redis = None
        return self._redis

    def _key(self, session_id: str) -> str:
        return f"vicap:session:{session_id}"

    async def save(self, session: SessionMemory) -> None:
        self._memory[session.session_id] = session
        redis = await self._get_redis()
        if redis:
            await redis.set(self._key(session.session_id), json.dumps(session.to_dict()))

    async def get(self, session_id: str) -> SessionMemory | None:
        if session_id in self._memory:
            return self._memory[session_id]
        redis = await self._get_redis()
        if redis:
            raw = await redis.get(self._key(session_id))
            if raw:
                session = SessionMemory.from_dict(json.loads(raw))
                self._memory[session_id] = session
                return session
        return None

    async def delete(self, session_id: str) -> None:
        self._memory.pop(session_id, None)
        redis = await self._get_redis()
        if redis:
            await redis.delete(self._key(session_id))

    async def list_ids(self) -> list[str]:
        return list(self._memory.keys())
