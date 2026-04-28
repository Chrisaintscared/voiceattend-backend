from fastapi import APIRouter, File, HTTPException, UploadFile, Depends
from app.database import get_all_logs, get_logs_by_user, save_attendance
from app.security import get_current_user

router = APIRouter(tags=["attendance"])


# ── POST /attendance/mark ─────────────────────────────────────────────────────
@router.post("/mark")
async def mark_attendance(audio: UploadFile = File(...), user=Depends(get_current_user)):
    log = save_attendance(user["name"])
    return {
        "status": "success",
        "user_name": user["name"],
        "confidence": 99.0,
        "log": log,
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
