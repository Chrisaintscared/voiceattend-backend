"""
VoiceAttend AI — main.py
========================
Render-safe FastAPI entry point for a voice biometric attendance system.

Design rules enforced here
──────────────────────────
* ML model is loaded ONCE, in startup(), stored in app.state.verifier.
* Routes NEVER import or initialise ML models themselves.
* A failed DB or ML init MUST NOT crash the server process.
* app.state.verifier is always set (to a verifier or None) before the
  first HTTP request can arrive, so routes never raise AttributeError.
* Routes must check `if request.app.state.verifier is None` and return
  HTTP 503 before attempting any inference.
"""

from __future__ import annotations

import traceback
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# Logging — structured output is friendlier in Render's log viewer
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("voiceattend")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="VoiceAttend AI",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
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
# Prefixes live HERE only — route files must NOT repeat the prefix.
#
#   /auth/...
#   /admin/...
#   /attendance/check-in
#   /classes/...
#   /voice/enroll
# ---------------------------------------------------------------------------
try:
    from app.routes import auth, admin, attendance, classes, enroll

    app.include_router(auth.router,        prefix="/auth",       tags=["auth"])
    app.include_router(admin.router,       prefix="/admin",      tags=["admin"])
    app.include_router(attendance.router,  prefix="/attendance", tags=["attendance"])
    app.include_router(classes.router,     prefix="/classes",    tags=["classes"])
    app.include_router(enroll.router,      prefix="/voice",      tags=["enroll"])

    log.info("✅ All routers registered")

except Exception as exc:                          # pragma: no cover
    log.error("❌ Router registration failed: %s", exc)
    traceback.print_exc()
    # Server still starts — routes simply won't exist for the failed module.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init_db() -> None:
    """Initialise database schema. Raises on failure (caller catches)."""
    from app.database import init_db  # local import keeps startup modular
    init_db()


def _load_speaker_model():
    """
    Load the SpeechBrain ECAPA-TDNN model synchronously.

    Returns the loaded SpeakerRecognition instance on success, or None on
    any failure.  This function is intentionally side-effect-free with
    respect to app.state so it can be unit-tested in isolation.

    CRITICAL import note
    ────────────────────
    speechbrain >= 1.0 moved SpeakerRecognition to
        speechbrain.inference.speaker
    The legacy path  speechbrain.pretrained  raises ModuleNotFoundError on
    current Render build images and must NEVER be used.
    """
    try:
        # ── Correct import path (speechbrain >= 1.0) ───────────────────────
        from speechbrain.inference.speaker import SpeakerRecognition   # noqa: PLC0415

        log.info("⏳ Loading ECAPA-TDNN speaker-verification model …")

        verifier = SpeakerRecognition.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir="pretrained_models/spkrec-ecapa-voxceleb",
            # ── CPU-only: Render free tier has no GPU ──────────────────────
            run_opts={"device": "cpu"},
        )

        log.info("✅ Speaker-verification model loaded (ECAPA-TDNN, CPU)")
        return verifier

    except ModuleNotFoundError as exc:
        log.error(
            "❌ SpeechBrain import failed — check installed version.\n"
            "   Required: speechbrain >= 1.0  (inference.speaker path)\n"
            "   Error   : %s",
            exc,
        )
        traceback.print_exc()
        return None

    except Exception as exc:            # network error, disk full, OOM, etc.
        log.error("❌ Speaker model failed to load: %s", exc)
        traceback.print_exc()
        return None


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
# Render free tier can take 30–60 s to cold-start.  We keep the event loop
# unblocked by running the CPU-heavy model download/load in a thread pool so
# that Render's health-check HTTP request can be answered immediately
# (model_loaded: false) while the model is still loading in the background.
#
# Flow
# ────
#  1. app.state.verifier = None         ← set synchronously, before any I/O
#  2. DB init (fast, network-bound)     ← awaited in thread pool
#  3. ML model load (slow, CPU-bound)   ← launched as background task
#     Health check returns model_loaded: false until it completes.

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="voiceattend-init")


async def _background_model_load() -> None:
    """Run model loading off the event loop, then store result in app.state."""
    loop = asyncio.get_event_loop()
    verifier = await loop.run_in_executor(_executor, _load_speaker_model)
    app.state.verifier = verifier       # atomic assignment — thread-safe in CPython

    if verifier is None:
        log.warning(
            "⚠️  Speaker model unavailable — enroll/verify endpoints will "
            "return HTTP 503 until the service restarts with a working model."
        )
    else:
        log.info("🎙️  Voice verification ready — system fully operational")


@app.on_event("startup")
async def startup() -> None:
    # ── 0. Sentinel — always set FIRST so routes never hit AttributeError ──
    app.state.verifier = None

    # ── 1. Database ────────────────────────────────────────────────────────
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _init_db)
        log.info("✅ Database initialised")
    except Exception as exc:
        log.error("❌ DB initialisation failed (system may be degraded): %s", exc)
        traceback.print_exc()
        # Continue — ML + routes still start even without DB.

    # ── 2. ML model (non-blocking background task) ─────────────────────────
    asyncio.create_task(_background_model_load())
    log.info("⏳ Speaker model loading in background …")

    log.info("🚀 VoiceAttend AI startup complete (model loading continues in background)")


# ---------------------------------------------------------------------------
# Shutdown — clean up thread pool
# ---------------------------------------------------------------------------
@app.on_event("shutdown")
async def shutdown() -> None:
    _executor.shutdown(wait=False)
    log.info("👋 VoiceAttend AI shut down")


# ---------------------------------------------------------------------------
# Health check
# ────────────────────────────────────────────────────────────────────────────
# Point Render's health-check URL at "/".
# Returns model_loaded: false while the background task is still loading;
# Flutter / dashboards can poll this and surface a "warming up" banner.
# ---------------------------------------------------------------------------
@app.get("/", tags=["health"])
def root() -> dict:
    model_ready: bool = getattr(app.state, "verifier", None) is not None
    return {
        "status": "ok",
        "model_loaded": model_ready,
    }


@app.get("/health", tags=["health"])
def health() -> dict:
    """Alias for Render's configurable health-check path."""
    return root()
