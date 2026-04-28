from fastapi import APIRouter, File, HTTPException, UploadFile, Depends
from app.security import get_current_user
from app.services.voice_service import extract_voice_embedding
from app.database import save_voice_profile, get_voice_profile

router = APIRouter(tags=["enroll"])


@router.post("/enroll-voice")
async def enroll_voice(
    voice: UploadFile = File(...),
    user=Depends(get_current_user)
):
    if user["role"] != "student":
        raise HTTPException(
            status_code=403,
            detail="Only students can enroll voice"
        )

    audio_bytes = await voice.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    try:
        embedding = extract_voice_embedding(audio_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Voice processing failed: {e}"
        )

    import json
    profile = save_voice_profile(user["id"], json.dumps(embedding))

    return {
        "message": "Voice enrolled successfully",
        "user_id": user["id"],
        "user_name": user["name"],
    }


@router.get("/enroll-status")
def enroll_status(user=Depends(get_current_user)):
    profile = get_voice_profile(user["id"])
    return {
        "enrolled": profile is not None,
        "user_id": user["id"],
    }
