from fastapi import APIRouter, File, UploadFile, Depends, HTTPException
from app.database import get_all_logs, get_logs_by_user, save_attendance
from app.security import get_current_user

router = APIRouter(prefix="/attendance", tags=["attendance"])


# ─────────────────────────────
# TEST ROUTE
# ─────────────────────────────
@router.get("/test")
def test():
    return {
        "status": "ok",
        "message": "attendance router working"
    }


# ─────────────────────────────
# CHECK-IN (VOICE AUDIO UPLOAD)
# ─────────────────────────────
@router.post("/mark")
async def mark_attendance(
    audio: UploadFile = File(...),
    user=Depends(get_current_user)
):
    try:
        # DEBUG LOGS (keep during testing)
        print("USERNAME:", user["name"])
        print("FILENAME:", audio.filename)
        print("CONTENT TYPE:", audio.content_type)

        # Validate file
        if not audio:
            raise HTTPException(status_code=400, detail="No audio uploaded")

        if not audio.content_type.startswith("audio"):
            raise HTTPException(
                status_code=400,
                detail="Uploaded file must be audio"
            )

        # Save attendance
        log = save_attendance(user["name"])

        return {
            "status": "success",
            "user_name": user["name"],
            "confidence": 99.0,
            "log": log
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────
# LOGS (ALL USERS)
# ─────────────────────────────
@router.get("/logs")
def logs():
    return {"logs": get_all_logs()}


# ─────────────────────────────
# LOGS (BY USER)
# ─────────────────────────────
@router.get("/logs/{user_name}")
def user_logs(user_name: str):
    return {
        "user_name": user_name,
        "logs": get_logs_by_user(user_name)
    }
