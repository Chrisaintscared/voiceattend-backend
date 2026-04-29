import traceback

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="VoiceAttend AI", version="1.0.0")

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers — imported once at module level, NEVER inside request handlers.
# Prefix lives HERE only; route files must NOT repeat the prefix.
#
#   Expected route shapes:
#     /auth/...
#     /admin/...
#     /attendance/check-in   ← attendance.router has NO "/attendance" prefix
#     /classes/...
#     /voice/enroll          ← enroll.router has NO "/voice" prefix
# ---------------------------------------------------------------------------
try:
    from app.routes import auth, admin, attendance, classes, enroll

    app.include_router(auth.router,        prefix="/auth",       tags=["auth"])
    app.include_router(admin.router,       prefix="/admin",      tags=["admin"])
    app.include_router(attendance.router,  prefix="/attendance", tags=["attendance"])
    app.include_router(classes.router,     prefix="/classes",    tags=["classes"])
    app.include_router(enroll.router,      prefix="/voice",      tags=["enroll"])

    print("✅ Routes loaded successfully")
except Exception as e:
    print(f"❌ Route import failed: {e}")
    traceback.print_exc()


# ---------------------------------------------------------------------------
# Startup — DB + ML model loaded ONCE here, stored in app.state.
#
# SpeechBrain ECAPA-TDNN is heavy; preloading avoids per-request cold cost
# and keeps Render free-tier from timing out on the first real request.
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup() -> None:
    # ── 1. Database ──────────────────────────────────────────────────────────
    try:
        from app.database import init_db
        init_db()
        print("✅ DB initialized")
    except Exception as e:
        print(f"❌ DB initialization failed: {e}")
        traceback.print_exc()

    # ── 2. Speaker-verification model (SpeechBrain ECAPA-TDNN) ──────────────
    # Loaded once into app.state.verifier so every route can reach it via
    #   request.app.state.verifier
    # without re-importing or re-instantiating.
    app.state.verifier = None          # sentinel — always set before routes run
    try:
        from speechbrain.pretrained import SpeakerRecognition

        print("⏳ Loading speaker-verification model (ECAPA-TDNN) …")
        verifier = SpeakerRecognition.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir="pretrained_models/spkrec-ecapa-voxceleb",
            run_opts={"device": "cpu"},   # Render free tier has no GPU
        )
        app.state.verifier = verifier
        print("✅ Model loaded (SpeechBrain ECAPA-TDNN)")
    except Exception as e:
        # A missing model should not crash the whole service; routes that need
        # it must check `request.app.state.verifier is not None`.
        print(f"❌ Model loading failed: {e}")
        traceback.print_exc()


# ---------------------------------------------------------------------------
# Health-check — confirms both service liveness and model readiness.
# Render's health-check URL should point here.
# ---------------------------------------------------------------------------
@app.get("/", tags=["health"])
def root() -> dict:
    model_ready: bool = getattr(app.state, "verifier", None) is not None
    return {
        "status": "ok",
        "model_loaded": model_ready,
    }
