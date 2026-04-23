"""
VoiceAttend AI - Audio Utilities
===================================
Shared helper functions for audio validation, format detection,
and pre-processing before feeding into the voice model pipeline.
"""

import io
from typing import Optional

# Allowed MIME types accepted by the /mark endpoint
ALLOWED_AUDIO_TYPES = {
    "audio/wav",
    "audio/wave",
    "audio/x-wav",
    "audio/mpeg",      # mp3
    "audio/mp3",
    "audio/ogg",
    "audio/flac",
    "audio/x-flac",
    "application/octet-stream",  # Generic fallback – still try to decode
}

# Maximum file size accepted (bytes)  →  10 MB
MAX_AUDIO_SIZE_BYTES = 10 * 1024 * 1024


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_audio_file(
    content_type: Optional[str],
    file_size: int,
) -> tuple[bool, str]:
    """
    Validate an uploaded audio file before processing.

    Args:
        content_type: MIME type reported by the client (may be None).
        file_size:    File size in bytes.

    Returns:
        (is_valid: bool, error_message: str)
        error_message is an empty string when is_valid is True.
    """
    if file_size == 0:
        return False, "Audio file is empty."

    if file_size > MAX_AUDIO_SIZE_BYTES:
        mb = MAX_AUDIO_SIZE_BYTES // (1024 * 1024)
        return False, f"File too large. Maximum allowed size is {mb} MB."

    if content_type and content_type not in ALLOWED_AUDIO_TYPES:
        allowed = ", ".join(sorted(ALLOWED_AUDIO_TYPES))
        return False, (
            f"Unsupported audio format '{content_type}'. "
            f"Allowed types: {allowed}"
        )

    return True, ""


# ---------------------------------------------------------------------------
# Format Detection (magic-bytes heuristic)
# ---------------------------------------------------------------------------

def detect_audio_format(audio_bytes: bytes) -> str:
    """
    Guess the audio container format from the first few bytes (magic bytes).

    Args:
        audio_bytes: Raw audio data.

    Returns:
        Format string: "wav", "mp3", "ogg", "flac", or "unknown".
    """
    if len(audio_bytes) < 4:
        return "unknown"

    header = audio_bytes[:4]

    if header[:4] == b"RIFF":
        return "wav"
    if header[:3] == b"ID3" or header[:2] == b"\xff\xfb":
        return "mp3"
    if header[:4] == b"OggS":
        return "ogg"
    if header[:4] == b"fLaC":
        return "flac"

    return "unknown"


# ---------------------------------------------------------------------------
# Duration Estimate (WAV only)
# ---------------------------------------------------------------------------

def estimate_wav_duration(audio_bytes: bytes) -> Optional[float]:
    """
    Estimate playback duration (seconds) of a WAV file without librosa.
    Returns None for non-WAV data or malformed headers.

    Args:
        audio_bytes: Raw WAV bytes.

    Returns:
        Duration in seconds, or None.
    """
    if detect_audio_format(audio_bytes) != "wav":
        return None
    try:
        import wave
        with wave.open(io.BytesIO(audio_bytes)) as wf:
            frames     = wf.getnframes()
            frame_rate = wf.getframerate()
            return frames / float(frame_rate)
    except Exception:
        return None
