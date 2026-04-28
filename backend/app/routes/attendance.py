from fastapi import APIRouter, File, HTTPException, UploadFile, Depends
from app.database import get_all_logs, get_logs_by_user, save_attendance
from app.security import get_current_user

router = APIRouter(tags=["attendance"])


# ── POST /attendance/mark ─────────────────────────────────────────────────────
@router.post("/mark")
async def mark_attendance(audio: UploadFile = File(...)):
    from app.services.voice_service import extract_voice_embedding, find_best_match
    from app.database import get_all_voice_profiles, get_user_by_id

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    try:
        query_emb = extract_voice_embedding(audio_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Voice processing failed: {e}")

    profiles = get_all_voice_profiles()
    if not profiles:
        raise HTTPException(status_code=404, detail="No voice profiles enrolled")

    match, score = find_best_match(query_emb, profiles)
    if not match:
        raise HTTPException(
            status_code=401,
            detail=f"Voice not recognised (score: {score:.3f})"
        )

    user = get_user_by_id(match["user_id"])
    log = save_attendance(user["name"])

    return {
        "status": "success",
        "user_name": user["name"],
        "confidence": round(score * 100, 1),
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
