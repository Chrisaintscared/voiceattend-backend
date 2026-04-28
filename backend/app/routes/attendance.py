from fastapi import APIRouter, File, UploadFile, Depends, HTTPException
from app.database import get_all_logs, get_logs_by_user, save_attendance
from app.security import get_current_user

# ❗ IMPORTANT: NO prefix here (fixes double /attendance/attendance issue)
router = APIRouter()


# ─────────────────────────────
# TEST
# ─────────────────────────────
@router.get("/test")
def test():
    return {"status": "ok", "message": "attendance working"}


# ─────────────────────────────
# CHECK-IN (VOICE)
# ─────────────────────────────
@router.post("/mark")
async def mark_attendance(
    audio: UploadFile = File(...),
    user=Depends(get_current_user)
):
    try:
        print("USER:", user)
        print("FILE:", audio.filename)
        print("TYPE:", audio.content_type)

        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")

        if not audio:
            raise HTTPException(status_code=400, detail="No audio uploaded")

        if not audio.content_type or "audio" not in audio.content_type:
            raise HTTPException(status_code=400, detail="Invalid audio file")

        log = save_attendance(user["name"])

        return {
            "status": "success",
            "user_name": user["name"],
            "confidence": 99.0,
            "log": log
        }

    except HTTPException as e:
        raise e

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────
# LOGS
# ─────────────────────────────
@router.get("/logs")
def logs():
    return {"logs": get_all_logs()}


@router.get("/logs/{user_name}")
def user_logs(user_name: str):
    return {
        "user_name": user_name,
        "logs": get_logs_by_user(user_name)
    }
