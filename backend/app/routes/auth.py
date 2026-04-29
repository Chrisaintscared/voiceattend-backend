"""
VoiceAttend AI — app/routes/auth.py
====================================
Authentication routes: register, login, voice-login, change-password.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.database import (
    create_user,
    get_all_voice_profiles,
    get_user_by_email,
    get_user_by_id,
    get_user_by_id_internal,
    update_user_password,
)
from app.security import (
    create_access_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)

log = logging.getLogger("voiceattend.auth")

router = APIRouter(tags=["auth"])

VOICE_MATCH_THRESHOLD: float = 0.75


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response models
# ─────────────────────────────────────────────────────────────────────────────

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


class DevResetRequest(BaseModel):
    email: str
    new_password: str
    secret: str


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe_user(user: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in user.items() if k != "password_hash"}


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    norm_a = np.linalg.norm(va)
    norm_b = np.linalg.norm(vb)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(va / norm_a, vb / norm_b))


def _best_voice_match(
    query_emb: list[float],
    profiles: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, float]:
    best_profile: dict[str, Any] | None = None
    best_score: float = -1.0

    for profile in profiles:
        raw = profile.get("embedding")
        if not raw:
            continue
        if isinstance(raw, str):
            import json
            try:
                raw = json.loads(raw)
            except Exception:
                log.warning("Skipping unparseable embedding for profile %s", profile.get("id"))
                continue
        score = _cosine_similarity(query_emb, raw)
        if score > best_score:
            best_score = score
            best_profile = profile

    if best_score >= VOICE_MATCH_THRESHOLD:
        return best_profile, best_score
    return None, best_score


# ─────────────────────────────────────────────────────────────────────────────
# REGISTER
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/register", status_code=201)
async def register(data: RegisterRequest):
    if get_user_by_email(data.email):
        raise HTTPException(status_code=409, detail="Email already registered")

    user = create_user(
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.password),
        role=data.role,
    )

    token = create_access_token(str(user["id"]), user["role"])

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": _safe_user(user),
    }


# ─────────────────────────────────────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/login")
def login(data: LoginRequest):
    user = get_user_by_email(data.email)

    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(str(user["id"]), user["role"])

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": _safe_user(user),
    }


# ─────────────────────────────────────────────────────────────────────────────
# VOICE LOGIN
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/voice-login")
async def voice_login(
    request: Request,
    voice: UploadFile = File(...),
):
    verifier = getattr(request.app.state, "verifier", None)
    if verifier is None:
        raise HTTPException(
            status_code=503,
            detail="Voice model is not ready. Please retry in a moment.",
        )

    audio_bytes = await voice.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    try:
        from app.services.voice_service import extract_embedding_from_bytes

        query_emb: list[float] = extract_embedding_from_bytes(
            audio_bytes=audio_bytes,
            verifier=verifier,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        log.exception("Embedding extraction failed during voice-login")
        raise HTTPException(
            status_code=422,
            detail=f"Voice processing failed: {exc}",
        )

    profiles = get_all_voice_profiles()
    if not profiles:
        raise HTTPException(
            status_code=404,
            detail="No voice profiles enrolled yet",
        )

    best_profile, score = _best_voice_match(query_emb, profiles)

    if best_profile is None:
        log.info("Voice-login rejected — best cosine score %.4f < %.2f", score, VOICE_MATCH_THRESHOLD)
        raise HTTPException(
            status_code=401,
            detail=(
                f"Voice not recognised "
                f"(similarity {score:.3f} < threshold {VOICE_MATCH_THRESHOLD})"
            ),
        )

    user = get_user_by_id(best_profile["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="Matched user account not found")

    token = create_access_token(str(user["id"]), user["role"])

    log.info(
        "Voice-login accepted — user_id=%s name=%s similarity=%.4f",
        user["id"],
        user.get("name"),
        score,
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": _safe_user(user),
        "voice_match": {
            "matched_name": user["name"],
            "confidence": round(score * 100, 2),
            "similarity": round(score, 4),
            "threshold": VOICE_MATCH_THRESHOLD,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# CHANGE PASSWORD
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/change-password")
def change_password(
    data: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
):
    full_user = get_user_by_id_internal(current_user["id"])
    if not full_user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(data.current_password, full_user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if len(data.new_password) < 8:
        raise HTTPException(
            status_code=400,
            detail="New password must be at least 8 characters",
        )

    update_user_password(current_user["id"], hash_password(data.new_password))

    return {"detail": "Password changed successfully"}


