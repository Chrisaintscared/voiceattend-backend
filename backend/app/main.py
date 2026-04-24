from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import traceback
import sys

app = FastAPI(title="VoiceAttend AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    try:
        print("▶ Importing database...")
        from app.database import init_db
        print("▶ Running init_db...")
        init_db()
        print("✅ init_db complete")
    except Exception as e:
        print("❌ STARTUP FAILED:", e)
        traceback.print_exc()
        sys.exit(1)

try:
    print("▶ Importing routes...")
    from app.routes import auth, admin, attendance
    print("✅ Routes imported")
    app.include_router(auth.router)
    app.include_router(admin.router,      prefix="/admin")
    app.include_router(attendance.router, prefix="/attendance")
    print("✅ Routes registered")
except Exception as e:
    print("❌ ROUTE IMPORT FAILED:", e)
    traceback.print_exc()
    sys.exit(1)

@app.get("/")
def root():
    return {"status": "ok"}
