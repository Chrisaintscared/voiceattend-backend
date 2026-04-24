from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel

from app.database import (
    get_user_by_email,
    create_user,
    save_voice_profile,
    get_all_voice_profiles,
    get_user_by_id,
)
from app.security import hash_password, verify_password, create_access_token
from app.services.voice_service import extract_voice_embedding, find_best_match

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


# ── POST /register ──────────────────────────────────────────────────────────
@router.post("/register")
async def register(
    name:     str        = Form(...),
    email:    str        = Form(...),
    password: str        = Form(...),
    voice:    UploadFile = File(...),
):
    if get_user_by_email(email):
        raise HTTPException(status_code=409, detail="Email already registered")

    audio_bytes = await voice.read()
    try:
        embedding = extract_voice_embedding(audio_bytes)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Voice processing failed: {exc}")

    user = create_user(name=name, email=email, password_hash=hash_password(password))
    save_voice_profile(user["id"], embedding)

    token = create_access_token(str(user["id"]), user["role"])
    return {"access_token": token, "token_type": "bearer", "user": user}


# ── POST /login ──────────────────────────────────────────────────────────────
@router.post("/login")
def login(data: LoginRequest):
    user = get_user_by_email(data.email)
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(str(user["id"]), user["role"])
    safe  = {k: v for k, v in user.items() if k != "password_hash"}
    return {"access_token": token, "token_type": "bearer", "user": safe}


# ── POST /voice-login ─────────────────────────────────────────────────────────
@router.post("/voice-login")
async def voice_login(voice: UploadFile = File(...)):
    audio_bytes = await voice.read()
    try:
        query_emb = extract_voice_embedding(audio_bytes)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Voice processing failed: {exc}")

    profiles = get_all_voice_profiles()
    if not profiles:
        raise HTTPException(status_code=404, detail="No voice profiles enrolled")

    match, score = find_best_match(query_emb, profiles)
    if not match:
        raise HTTPException(status_code=401, detail=f"Voice not recognised (score: {score:.3f})")

    user  = get_user_by_id(match["user_id"])
    token = create_access_token(str(user["id"]), user["role"])
    safe  = {k: v for k, v in user.items() if k != "password_hash"}
    return {"access_token": token, "token_type": "bearer", "user": safe}
