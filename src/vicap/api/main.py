from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from vicap.config import ROOT, get_settings
from vicap.core.db import init_db, close_db
from vicap.core.exceptions import app_exception_handler, http_exception_handler, AppException
from vicap.api.v1.router import v1_router

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

app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)

app.include_router(v1_router)

DEMO_DIR = ROOT / "demo"
if DEMO_DIR.exists():
    app.mount("/demo", StaticFiles(directory=str(DEMO_DIR), html=True), name="demo")

    @app.get("/")
    async def root():
        return FileResponse(DEMO_DIR / "index.html")


@app.on_event("startup")
async def on_startup() -> None:
    settings = get_settings()
    if settings.database_url:
        try:
            await init_db()
            logger.info("Database connected and tables created")
        except Exception as exc:
            logger.warning("Database init failed (non-fatal): %s", exc)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await close_db()
