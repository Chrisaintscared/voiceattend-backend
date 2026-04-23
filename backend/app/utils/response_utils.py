"""
VoiceAttend AI - Response Helpers
=====================================
Standardised response builders so every endpoint returns a consistent
JSON envelope, making it easier for the Flutter client to parse.
"""

from datetime import datetime, timezone
from typing import Any, Optional


def success_response(data: Any, message: str = "Request successful.") -> dict:
    """
    Build a standardised success envelope.

    Args:
        data:    The main payload to include under the "data" key.
        message: Human-readable success message.

    Returns:
        dict: { status, message, data, timestamp }
    """
    return {
        "status":    "success",
        "message":   message,
        "data":      data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def error_response(message: str, code: Optional[int] = None) -> dict:
    """
    Build a standardised error envelope.

    Args:
        message: Human-readable error description.
        code:    Optional application-level error code.

    Returns:
        dict: { status, message, code, timestamp }
    """
    return {
        "status":    "error",
        "message":   message,
        "code":      code,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
