from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import auth, admin, attendance
from app.database import init_db

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
    init_db()

# Routes — no prefixes on auth so /register /login /voice-login are root-level
app.include_router(auth.router)
app.include_router(admin.router,      prefix="/admin")
app.include_router(attendance.router, prefix="/attendance")

@app.get("/")
def root():
    return {"status": "ok"}
