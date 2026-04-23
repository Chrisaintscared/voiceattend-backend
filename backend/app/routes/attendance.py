from fastapi import APIRouter, File, HTTPException, UploadFile

from app.database import get_all_logs, get_logs_by_user, save_attendance
from app.models.voice_model import process_audio

router = APIRouter(tags=["attendance"])


# ── POST /attendance/mark ─────────────────────────────────────────────────────
@router.post("/mark")
async def mark_attendance(audio: UploadFile = File(...)):
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    result     = process_audio(audio_bytes)
    user_name  = result["user_name"]
    confidence = result["confidence"]
    log        = save_attendance(user_name)

    return {
        "status":     "success",
        "user_name":  user_name,
        "confidence": confidence,
        "log":        log,
    }


# ── GET /attendance/test ──────────────────────────────────────────────────────
@router.get("/test")
def test():
    return {"status": "ok", "message": "attendance router live"}


# ── GET /attendance/logs ──────────────────────────────────────────────────────
@router.get("/logs")
def logs():
    return {"logs": get_all_logs()}


# ── GET /attendance/logs/{user_name} ─────────────────────────────────────────
@router.get("/logs/{user_name}")
def user_logs(user_name: str):
    return {"user_name": user_name, "logs": get_logs_by_user(user_name)}
