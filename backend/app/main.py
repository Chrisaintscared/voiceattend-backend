from __future__ import annotations

import asyncio
import logging
import traceback
from contextlib import asynccontextmanager

import torch
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ── RAM optimisation (must happen before any model import) ────────────────────
torch.set_grad_enabled(False)   # no autograd needed at inference
torch.set_num_threads(1)        # prevent RAM spikes from threading

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("voiceattend")


# ── DB init (run in thread so it doesn't block the event loop) ────────────────
def _init_db() -> None:
    from app.database import init_db
    init_db()


# ── Lifespan (replaces deprecated @app.on_event) ─────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _init_db)
        log.info("✅ Database initialised")
    except Exception as exc:
        log.error("❌ DB initialisation failed: %s", exc)

    log.info("🚀 VoiceAttend AI ready (X-Vector On-Demand Mode)")
    yield
    # --- shutdown (add cleanup here if needed) ---
    log.info("👋 VoiceAttend shutting down")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="VoiceAttend AI",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
try:
    from app.routes import attendance, auth, admin, classes, enroll

    app.include_router(auth.router,        prefix="/auth",       tags=["auth"])
    app.include_router(admin.router,       prefix="/admin",      tags=["admin"])
    app.include_router(attendance.router,  prefix="/attendance", tags=["attendance"])
    app.include_router(classes.router,     prefix="/classes",    tags=["classes"])
    app.include_router(enroll.router,      prefix="/voice",      tags=["enroll"])

    log.info("✅ All routers registered")
except Exception as exc:
    log.error("❌ Router registration failed: %s", exc)
    traceback.print_exc()


# ── Health endpoints ──────────────────────────────────────────────────────────
@app.get("/", tags=["health"])
def root() -> dict:
    return {"status": "ok", "mode": "x-vector-optimized"}


@app.get("/health", tags=["health"])
def health() -> dict:
    return root()
    
from app.routes import router as api_router

app.include_router(api_router)
