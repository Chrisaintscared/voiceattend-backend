from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import traceback
import asyncio

app = FastAPI(title="VoiceAttend AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# import routes safely
try:
    from app.routes import auth, admin, attendance, classes, enroll
    app.include_router(auth.router,       prefix="/auth",       tags=["auth"])
    app.include_router(admin.router,      prefix="/admin",      tags=["admin"])
    app.include_router(attendance.router, prefix="/attendance", tags=["attendance"])
    app.include_router(classes.router,    prefix="/classes",    tags=["classes"])
    app.include_router(enroll.router,     prefix="/voice",      tags=["enroll"])
    print("✅ Routes loaded")
except Exception as e:
    print("❌ Route import failed:", e)
    traceback.print_exc()

@app.on_event("startup")
async def startup():
    # Init DB
    try:
        from app.database import init_db
        init_db()
        print("✅ DB initialized")
    except Exception as e:
        print("⚠️ DB init failed (non-fatal):", e)
        traceback.print_exc()

    # Pre-load voice encoder in background thread so it doesn't block requests
    try:
        from app.services.voice_service import _get_encoder
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _get_encoder)
        print("🔊 Voice encoder pre-loaded")
    except Exception as e:
        print("⚠️ Voice encoder pre-load failed (non-fatal):", e)
        traceback.print_exc()

@app.get("/")
def root():
    return {"status": "ok"}
