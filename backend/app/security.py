"""
security.py — JWT tokens and password hashing utilities.
Fixed version (bcrypt-safe + no 72-byte crash issue)
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
import hashlib

from app.config import settings
from app import database as db

# ─────────────────────────────────────────────
# Password hashing (FIXED SAFE VERSION)
# ─────────────────────────────────────────────

# Keep bcrypt but make it stable
_pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)


def _normalize_password(password: str) -> str:
    """
    Fix bcrypt 72-byte limit issue safely.
    We hash long passwords BEFORE bcrypt.
    """
    return hashlib.sha256(password.encode()).hexdigest()


def hash_password(plain: str) -> str:
    """
    Hash password safely (no bcrypt crash).
    """
    safe_password = _normalize_password(plain)
    return _pwd_context.hash(safe_password)


def verify_password(plain: str, hashed: str) -> bool:
    """
    Verify password safely.
    """
    safe_password = _normalize_password(plain)
    return _pwd_context.verify(safe_password, hashed)


# ─────────────────────────────────────────────
# JWT AUTH
# ─────────────────────────────────────────────

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def create_access_token(
    user_id: str,
    role: str,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create JWT token.
    """
    expire = datetime.now(timezone.utc) + (
        expires_delta
        or timedelta(minutes=settings.access_token_expire_minutes)
    )

    payload = {
        "sub": user_id,
        "role": role,
        "exp": expire
    }

    return jwt.encode(
        payload,
        settings.secret_key,
        algorithm=settings.algorithm
    )


def decode_token(token: str) -> dict:
    """
    Decode JWT token safely.
    """
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm]
        )

        user_id: str = payload.get("sub")
        if not user_id:
            raise credentials_exc

        return payload

    except JWTError:
        raise credentials_exc


# ─────────────────────────────────────────────
# FASTAPI DEPENDENCIES
# ─────────────────────────────────────────────

async def get_current_user(token: str = Depends(_oauth2_scheme)) -> dict:
    """
    Get current authenticated user.
    """
    payload = decode_token(token)

    user = db.get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    return user


async def require_admin(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Admin-only access.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return current_user