from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from vicap.config import ROOT, get_settings
from vicap.core.db import init_db, close_db
from vicap.core.exceptions import app_exception_handler, http_exception_handler, AppException
from vicap.api.v1.router import v1_router

logger = logging.getLogger(__name__)

# ── Prometheus metrics ──────────────────────────────────────────
HTTP_REQUESTS = Counter(
    "vicap_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
HTTP_LATENCY = Histogram(
    "vicap_http_latency_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
)
API_CALLS = Counter(
    "vicap_api_calls_total",
    "Total Fireworks API calls",
    ["model"],
)
TOKENS_USED = Counter(
    "vicap_tokens_total",
    "Total tokens consumed",
    ["model", "kind"],
)

# ── Rate limiter state (simple in-memory per-key, reset per minute) ──
_rate_limit_buckets: dict[str, dict[int, int]] = {}


def _check_rate_limit(api_key_id: str | None) -> None:
    if not api_key_id:
        return
    settings = get_settings()
    now_minute = int(time.time() // 60)
    bucket = _rate_limit_buckets.setdefault(api_key_id, {})
    bucket[now_minute] = bucket.get(now_minute, 0) + 1
    count = bucket[now_minute]

    # Clean old minute entries
    for key in list(bucket.keys()):
        if key < now_minute - 1:
            del bucket[key]

    if count > settings.rate_limit_per_minute:
        raise HTTPException(429, "Rate limit exceeded. Try again in 60 seconds.")


# ── App factory ──────────────────────────────────────────────────
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


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    method = request.method
    path = request.url.path

    start = time.perf_counter()
    response = await call_next(request)
    latency = time.perf_counter() - start

    HTTP_REQUESTS.labels(method=method, endpoint=path, status=response.status_code).inc()
    HTTP_LATENCY.labels(method=method, endpoint=path).observe(latency)

    return response


@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.on_event("startup")
async def on_startup() -> None:
    settings = get_settings()
    if settings.database_url:
        try:
            await init_db()
            logger.info("Database connected and tables created")
        except Exception as exc:
            logger.warning("Database init failed (non-fatal): %s", exc)
    logger.info("VICAP Studio started — metrics at /metrics, docs at /docs, API at /api/v1/")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await close_db()
