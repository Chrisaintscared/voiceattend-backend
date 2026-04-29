"""
VoiceAttend AI — app/config.py
================================
Centralised settings loaded from environment variables.

Design rules enforced here
──────────────────────────
* No insecure hardcoded defaults for secrets or DB credentials.
* secret_key and database_url are REQUIRED — missing either raises a clear
  ValueError at import time so the process never starts in a broken state.
* .env file is loaded only as a local-development convenience; on Render
  the real environment variables are injected by the platform and take
  precedence automatically (pydantic-settings env-var priority > .env).
* voice_similarity_threshold is validated to be strictly within [0.0, 1.0].
* All validation happens inside the model via @field_validator so the error
  messages are surfaced at startup, not buried in a runtime traceback.
"""

from __future__ import annotations

import secrets
from typing import Any

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # ── Required — no default, must be supplied via env ──────────────────────

    database_url: str           # e.g. postgresql://user:pass@host:5432/db
    secret_key: str             # random 32-byte hex; generate with: openssl rand -hex 32

    # ── JWT ───────────────────────────────────────────────────────────────────

    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440     # 24 hours

    # ── Voice / ML ────────────────────────────────────────────────────────────

    voice_similarity_threshold: float = 0.75    # cosine similarity accept threshold

    # ── General ───────────────────────────────────────────────────────────────

    app_name: str = "VoiceAttend AI"
    debug: bool = False

    # ── Pydantic-settings config ──────────────────────────────────────────────
    # env_file is a local-dev fallback only.
    # On Render, system env vars are injected directly and always take
    # precedence over anything in .env (pydantic-settings priority order:
    # init kwargs > env vars > .env file > field defaults).

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",         # silently ignore unknown env vars
        case_sensitive=False,   # DATABASE_URL and database_url both work
    )

    # ── Field validators ──────────────────────────────────────────────────────

    @field_validator("secret_key")
    @classmethod
    def _validate_secret_key(cls, v: str) -> str:
        """
        Reject obviously weak or placeholder secret keys.

        Rules
        ─────
        * Must not be empty.
        * Must not be any known placeholder string.
        * Must be at least 32 characters long to provide adequate HMAC entropy.
        """
        stripped = v.strip()

        if not stripped:
            raise ValueError(
                "SECRET_KEY is required and must not be empty. "
                "Generate one with:  openssl rand -hex 32"
            )

        _WEAK_PLACEHOLDERS = {
            "change_me", "changeme", "secret", "your-secret-key",
            "your_secret_key", "development", "dev", "test", "none",
        }
        if stripped.lower() in _WEAK_PLACEHOLDERS:
            raise ValueError(
                f"SECRET_KEY value '{stripped}' is an insecure placeholder. "
                "Set a strong random value in your environment. "
                "Generate one with:  openssl rand -hex 32"
            )

        if len(stripped) < 32:
            raise ValueError(
                f"SECRET_KEY must be at least 32 characters long "
                f"(got {len(stripped)}). "
                "Generate one with:  openssl rand -hex 32"
            )

        return stripped

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, v: str) -> str:
        """
        Ensure database_url is present and looks like a PostgreSQL URL.

        Render PostgreSQL and Supabase both use the standard
        postgresql:// or postgres:// scheme.
        """
        stripped = v.strip()

        if not stripped:
            raise ValueError(
                "DATABASE_URL is required and must not be empty. "
                "Set it to your PostgreSQL connection string, e.g.: "
                "postgresql://user:pass@host:5432/dbname"
            )

        _VALID_SCHEMES = ("postgresql://", "postgres://")
        if not any(stripped.startswith(scheme) for scheme in _VALID_SCHEMES):
            raise ValueError(
                f"DATABASE_URL must start with 'postgresql://' or 'postgres://'. "
                f"Got: '{stripped[:40]}...'"
            )

        return stripped

    @field_validator("voice_similarity_threshold")
    @classmethod
    def _validate_threshold(cls, v: float) -> float:
        """Cosine similarity is defined on [-1, 1]; a useful threshold is (0, 1]."""
        if not (0.0 < v <= 1.0):
            raise ValueError(
                f"VOICE_SIMILARITY_THRESHOLD must be a float in (0.0, 1.0]. "
                f"Got: {v}"
            )
        return v

    @field_validator("algorithm")
    @classmethod
    def _validate_algorithm(cls, v: str) -> str:
        """Only allow HMAC-SHA algorithms; RS256 requires key-pair setup."""
        _ALLOWED = {"HS256", "HS384", "HS512"}
        if v.upper() not in _ALLOWED:
            raise ValueError(
                f"ALGORITHM must be one of {sorted(_ALLOWED)}. Got: '{v}'"
            )
        return v.upper()

    @field_validator("access_token_expire_minutes")
    @classmethod
    def _validate_expiry(cls, v: int) -> int:
        if v < 1:
            raise ValueError(
                "ACCESS_TOKEN_EXPIRE_MINUTES must be at least 1. "
                f"Got: {v}"
            )
        if v > 43_200:   # 30 days
            raise ValueError(
                "ACCESS_TOKEN_EXPIRE_MINUTES exceeds 30 days (43 200 min). "
                "Use refresh tokens for long-lived sessions instead."
            )
        return v


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
# If any required env var is absent or fails validation, pydantic raises a
# ValidationError here — before the FastAPI app object is even created — so
# Render will surface the error in the build/startup logs immediately.

try:
    settings = Settings()  # type: ignore[call-arg]
except Exception as exc:   # ValidationError or missing-field error
    import sys
    # Print a human-readable summary so it's obvious in Render logs.
    print(
        "\n"
        "╔══════════════════════════════════════════════════════════╗\n"
        "║  VoiceAttend AI — CONFIGURATION ERROR (startup aborted)  ║\n"
        "╚══════════════════════════════════════════════════════════╝\n"
        f"{exc}\n\n"
        "Required environment variables:\n"
        "  DATABASE_URL              — PostgreSQL connection string\n"
        "  SECRET_KEY                — min 32-char random string\n"
        "                              (openssl rand -hex 32)\n\n"
        "Optional environment variables (with defaults shown):\n"
        "  ALGORITHM                 — HS256 | HS384 | HS512  (default: HS256)\n"
        "  ACCESS_TOKEN_EXPIRE_MINUTES — integer >= 1          (default: 1440)\n"
        "  VOICE_SIMILARITY_THRESHOLD  — float in (0, 1]       (default: 0.75)\n"
        "  DEBUG                     — true | false             (default: false)\n",
        file=sys.stderr,
    )
    sys.exit(1)
