import traceback

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="VoiceAttend AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# Prefix lives HERE only — route files must NOT repeat the prefix.
#
#   /auth/...
#   /admin/...
#   /attendance/check-in   ← attendance.router has NO "/attendance" prefix
#   /classes/...
#   /voice/enroll          ← enroll.router has NO "/voice" prefix
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
# Startup — DB init runs first, ML model second.
# A model failure MUST NOT prevent the service from starting.
# Routes check app.state.verifier is not None before running inference
# and return HTTP 503 if the model is unavailable.
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

    # ── 2. Speaker-verification model ────────────────────────────────────────
    # Sentinel: always set before any request can arrive so routes never hit
    # an AttributeError on app.state.verifier.
    app.state.verifier = None

    try:
        # FIX: speechbrain >= 1.0 moved SpeakerRecognition out of
        # speechbrain.pretrained into speechbrain.inference.speaker.
        # The old import path raises ModuleNotFoundError on Render.
        from speechbrain.inference.speaker import SpeakerRecognition

        print("⏳ Loading speaker-verification model (ECAPA-TDNN) …")

        verifier = SpeakerRecognition.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir="pretrained_models/spkrec-ecapa-voxceleb",
            run_opts={"device": "cpu"},   # Render free tier has no GPU
        )

        app.state.verifier = verifier
        print("✅ Model loaded (SpeechBrain ECAPA-TDNN)")

    except ModuleNotFoundError as e:
        print(f"❌ Voice model import failed (check speechbrain version): {e}")
        traceback.print_exc()

    except Exception as e:
        print(f"❌ Voice model failed to load: {e}")
        traceback.print_exc()

    # app.state.verifier remains None if either except branch was hit.
    # Routes return HTTP 503 when verifier is None (see enroll.py / attendance.py).


# ---------------------------------------------------------------------------
# Health check
# Render's health-check URL should point here.
# Returns model_loaded: false when the model failed to load so dashboards
# and the Flutter app can surface a clear "service degraded" warning.
# ---------------------------------------------------------------------------
@app.get("/", tags=["health"])
def root() -> dict:
    model_ready: bool = getattr(app.state, "verifier", None) is not None
    return {
        "status": "ok",
        "model_loaded": model_ready,
    }
