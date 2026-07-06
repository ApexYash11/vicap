from fastapi import APIRouter

from vicap.api.v1.health import router as health_router
from vicap.api.v1.sessions import router as sessions_router
from vicap.api.v1.jobs import router as jobs_router
from vicap.api.v1.clips import router as clips_router
from vicap.api.v1.admin import router as admin_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(health_router)
v1_router.include_router(sessions_router)
v1_router.include_router(jobs_router)
v1_router.include_router(clips_router)
v1_router.include_router(admin_router)

__all__ = ["v1_router"]
