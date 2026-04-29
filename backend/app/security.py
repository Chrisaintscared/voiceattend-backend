"""
VoiceAttend AI — app/security.py
==================================
JWT token creation/decoding and password hashing utilities.

Design rules enforced here
──────────────────────────
* Passwords are hashed directly with bcrypt via passlib — NO pre-hashing,
  NO SHA-256 normalisation, NO manual truncation.
  The SHA-256 workaround that existed previously was removed because:
    - it silently converts every password to a fixed-length hex digest,
      making all passwords effectively 64 ASCII characters long;
    - it breaks interoperability with any future auth system / admin tool;
    - the real bcrypt 72-byte problem is handled by passlib internally
      (passlib ≥ 1.7.4 with bcrypt ≥ 4.0 truncates at 72 bytes by design —
      an application-level SHA-256 wrapper is not the correct fix).
* JWT "sub" is always a string user_id; callers that need an int convert
  themselves (get_current_user does int() when fetching from the DB).
* All auth errors surface as HTTP 401 with a consistent message so clients
  cannot distinguish "bad token" from "user deleted".
* No DB logic lives here beyond the single get_user_by_id call required by
  the FastAPI dependency get_current_user.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext

from app.config import settings
from app import database as db

log = logging.getLogger("voiceattend.security")

# ─────────────────────────────────────────────────────────────────────────────
# Password hashing
# ─────────────────────────────────────────────────────────────────────────────
# bcrypt is the only active scheme.  "deprecated=auto" means any hash created
# with an older scheme is accepted for verification but re-hashed on next login
# (useful for future algorithm migrations).
#
# bcrypt 72-byte note
# ───────────────────
# bcrypt silently truncates input at 72 bytes.  For the vast majority of real
# passwords this is irrelevant.  If your policy requires support for passwords
# longer than 72 bytes, the correct fix is to enable the argon2 scheme in
# passlib (pip install argon2-cffi) and add it here — NOT to pre-hash with
# SHA-256, which causes its own problems (see module docstring).

_pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    # bcrypt work factor — 12 is a sane production default (adjust upward as
    # hardware improves; 10 is acceptable on Render free tier to avoid timeouts)
    bcrypt__rounds=12,
)


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """
    Return True if *plain* matches *hashed*.

    Raises nothing — passlib returns False for any mismatch or corrupt hash.
    """
    try:
        return _pwd_context.verify(plain, hashed)
    except Exception:
        # Malformed / incompatible hash stored in DB — treat as mismatch.
        log.warning("Password verification raised an exception — treating as mismatch")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# JWT
# ─────────────────────────────────────────────────────────────────────────────

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# Reusable exception so every auth failure looks identical to the client.
_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def create_access_token(
    user_id: str | int,
    role: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a signed JWT access token.

    Parameters
    ──────────
    user_id      : User primary key (str or int — stored as string in "sub").
    role         : User role string, e.g. "student" or "admin".
    expires_delta: Override the default expiry from settings.
    """
    expire = datetime.now(timezone.utc) + (
        expires_delta
        or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload = {
        "sub": str(user_id),   # "sub" must always be a string (JWT spec)
        "role": str(role),
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT token.

    Returns the payload dict on success.
    Raises HTTP 401 on any failure (expired, malformed, missing "sub").
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
    except ExpiredSignatureError:
        log.debug("JWT decode failed: token expired")
        raise _CREDENTIALS_EXCEPTION
    except JWTError as exc:
        log.debug("JWT decode failed: %s", exc)
        raise _CREDENTIALS_EXCEPTION

    user_id: str | None = payload.get("sub")
    if not user_id:
        log.debug("JWT decode failed: missing 'sub' claim")
        raise _CREDENTIALS_EXCEPTION

    return payload


# Backwards-compatibility alias used by other modules that imported the old name.
decode_access_token = decode_token


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI dependencies
# ─────────────────────────────────────────────────────────────────────────────

async def get_current_user(token: str = Depends(_oauth2_scheme)) -> dict:
    """
    FastAPI dependency — decode the Bearer token and return the matching user.

    Raises HTTP 401 if the token is invalid OR the user no longer exists.
    The caller receives a safe user dict (password_hash is not stripped here;
    callers that build API responses should strip it themselves via _safe_user).
    """
    payload = decode_token(token)           # raises 401 on any token failure

    raw_id: str = payload["sub"]

    # The DB primary key is an integer in PostgreSQL; convert safely.
    try:
        user_id = int(raw_id)
    except (ValueError, TypeError):
        log.warning("JWT 'sub' is not a valid integer: %r", raw_id)
        raise _CREDENTIALS_EXCEPTION

    user = db.get_user_by_id(user_id)
    if not user:
        # User was deleted after token was issued — treat as invalid credential.
        log.debug("get_current_user: user_id=%s not found in DB", user_id)
        raise _CREDENTIALS_EXCEPTION

    return user


async def require_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    FastAPI dependency — allow only users whose role is "admin".

    Raises HTTP 403 for any other role.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user
