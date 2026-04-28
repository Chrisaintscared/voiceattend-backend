from fastapi import APIRouter, File, UploadFile, Depends, HTTPException
from app.database import get_all_logs, get_logs_by_user, save_attendance
from app.security import get_current_user

router = APIRouter(prefix="/attendance", tags=["attendance"])


# ─────────────────────────────
# TEST ROUTE
# ─────────────────────────────
@router.get("/test")
def test():
    return {"status": "ok", "message": "attendance working"}


# ─────────────────────────────
# CHECK-IN (VOICE UPLOAD)
# ─────────────────────────────
@router.post("/mark")
async def mark_attendance(
    audio: UploadFile = File(...),
    user=Depends(get_current_user)
):
    try:
        # 🔥 DEBUG (important for your issue)
        print("USER:", user)
        print("FILE:", audio.filename)
        print("TYPE:", audio.content_type)

        # ❌ AUTH GUARD
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")

        # ❌ FILE CHECK
        if not audio:
            raise HTTPException(status_code=400, detail="No audio uploaded")

        if not audio.content_type or not audio.content_type.startswith("audio"):
            raise HTTPException(status_code=400, detail="Invalid audio file")

        # SAVE ATTENDANCE
        log = save_attendance(user["name"])

        return {
            "status": "success",
            "user_name": user["name"],
            "confidence": 99.0,
            "log": log
        }

    except HTTPException as e:
        # 🔥 IMPORTANT: show real error in Flutter
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
