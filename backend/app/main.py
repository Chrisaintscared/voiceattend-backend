from __future__ import annotations
import traceback
import asyncio
import logging
import torch  # <--- Added
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ── EXTREME RAM OPTIMIZATION ──
torch.set_grad_enabled(False)       # Disable gradients globally
torch.set_num_threads(1)            # Force 1 CPU thread to prevent RAM spikes
if torch.get_num_threads() > 1:
    torch.set_num_threads(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("voiceattend")

app = FastAPI(title="VoiceAttend AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    from app.routes import auth, admin, attendance, classes, enroll
    app.include_router(auth.router, prefix="/auth", tags=["auth"])
    app.include_router(admin.router, prefix="/admin", tags=["admin"])
    app.include_router(attendance.router, prefix="/attendance", tags=["attendance"])
    app.include_router(classes.router, prefix="/classes", tags=["classes"])
    app.include_router(enroll.router, prefix="/voice", tags=["enroll"])
    log.info("✅ All routers registered")
except Exception as exc:
    log.error("❌ Router registration failed: %s", exc)
    traceback.print_exc()

def _init_db() -> None:
    from app.database import init_db
    init_db()

@app.on_event("startup")
async def startup() -> None:
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _init_db)
        log.info("✅ Database initialised")
    except Exception as exc:
        log.error("❌ DB initialisation failed: %s", exc)
    log.info("🚀 VoiceAttend AI ready (X-Vector On-Demand Mode)")

@app.get("/", tags=["health"])
def root() -> dict:
    return {"status": "ok", "mode": "x-vector-optimized"}

@app.get("/health", tags=["health"])
def health() -> dict:
    return root()
