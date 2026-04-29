"""
VoiceAttend AI — main.py
========================
Render-optimized FastAPI entry point.
- Model is NOT loaded on startup to save RAM.
- Routes load the model on-demand and clear it after use.
"""

from __future__ import annotations
import traceback
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("voiceattend")

# ---------------------------------------------------------------------------
# App Init
# ---------------------------------------------------------------------------
app = FastAPI(
    title="VoiceAttend AI",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
try:
    from app.routes import auth, admin, attendance, classes, enroll

    app.include_router(auth.router,       prefix="/auth",        tags=["auth"])
    app.include_router(admin.router,       prefix="/admin",       tags=["admin"])
    app.include_router(attendance.router,  prefix="/attendance",  tags=["attendance"])
    app.include_router(classes.router,     prefix="/classes",     tags=["classes"])
    app.include_router(enroll.router,      prefix="/voice",       tags=["enroll"])

    log.info("✅ All routers registered")
except Exception as exc:
    log.error("❌ Router registration failed: %s", exc)
    traceback.print_exc()

# ---------------------------------------------------------------------------
# Database Initialization
# ---------------------------------------------------------------------------
def _init_db() -> None:
    from app.database import init_db
    init_db()

@app.on_event("startup")
async def startup() -> None:
    # ── 1. DB Init ─────────────────────────────────────────────────────────
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _init_db)
        log.info("✅ Database initialised")
    except Exception as exc:
        log.error("❌ DB initialisation failed: %s", exc)

    # ── 2. ML Sentinel ─────────────────────────────────────────────────────
    # We no longer load the model in the background. 
    # This keeps idle RAM usage under 200MB.
    log.info("🚀 VoiceAttend AI ready (Model will load on-demand for check-ins)")

# ---------------------------------------------------------------------------
# Health Checks
# ---------------------------------------------------------------------------
@app.get("/", tags=["health"])
def root() -> dict:
    return {
        "status": "ok",
        "mode": "on-demand-loading",
        "platform": "render-free-tier"
    }

@app.get("/health", tags=["health"])
def health() -> dict:
    return root()
