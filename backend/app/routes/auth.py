from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel

from app.database import (
    get_user_by_email,
    create_user,
    get_all_voice_profiles,
    get_user_by_id,
    get_user_by_id_internal,
    update_user_password,
)
from app.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_token,
    get_current_user,
)

router = APIRouter(tags=["auth"])


# ─────────────────────────────────────────────────────────────
# REQUEST MODELS
# ─────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    role: str = "student"


class LoginRequest(BaseModel):
    email: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


# ─────────────────────────────────────────────────────────────
# REGISTER
# ─────────────────────────────────────────────────────────────

@router.post("/register", status_code=201)
async def register(data: RegisterRequest):
    if get_user_by_email(data.email):
        raise HTTPException(status_code=409, detail="Email already registered")

    user = create_user(
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.password),
        role=data.role
    )

    token = create_access_token(str(user["id"]), user["role"])
    safe_user = {k: v for k, v in user.items() if k != "password_hash"}

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": safe_user
    }


# ─────────────────────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────────────────────

@router.post("/login")
def login(data: LoginRequest):
    user = get_user_by_email(data.email)

    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(str(user["id"]), user["role"])
    safe_user = {k: v for k, v in user.items() if k != "password_hash"}

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": safe_user
    }


# ─────────────────────────────────────────────────────────────
# VOICE LOGIN
# ─────────────────────────────────────────────────────────────

@router.post("/voice-login")
async def voice_login(voice: UploadFile = File(...)):
    from app.services.voice_service import extract_voice_embedding, find_best_match

    audio_bytes = await voice.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    try:
        query_emb = extract_voice_embedding(audio_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Voice processing failed: {exc}"
        )

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
    token = create_access_token(str(user["id"]), user["role"])
    safe_user = {k: v for k, v in user.items() if k != "password_hash"}

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": safe_user,
        "voice_match": {
            "matched_name": user["name"],
            "confidence": round(score * 100, 1)
        }
    }


# ─────────────────────────────────────────────────────────────
# CHANGE PASSWORD
# ─────────────────────────────────────────────────────────────

@router.post("/change-password")
def change_password(
    data: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
):
    # get_current_user may return a safe user (no password_hash),
    # so we re-fetch the full row for verification
    full_user = get_user_by_id_internal(current_user["id"])
    if not full_user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(data.current_password, full_user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if len(data.new_password) < 8:
        raise HTTPException(
            status_code=400,
            detail="New password must be at least 8 characters"
        )

    update_user_password(current_user["id"], hash_password(data.new_password))

    return {"detail": "Password changed successfully"}
