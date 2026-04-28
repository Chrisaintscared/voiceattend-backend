import json
import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, File, HTTPException, UploadFile, Depends

from app.security import get_current_user
from app.services.voice_service import extract_voice_embedding
from app.database import save_voice_profile, get_voice_profile

router = APIRouter(tags=["enroll"])

_executor = ThreadPoolExecutor(max_workers=1)


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
        loop = asyncio.get_event_loop()
        embedding = await asyncio.wait_for(
            loop.run_in_executor(_executor, extract_voice_embedding, audio_bytes),
            timeout=30.0
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="Voice processing timed out — please speak for 3-5 seconds and try again"
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Voice processing failed: {e}"
        )

    save_voice_profile(user["id"], json.dumps(embedding))

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
