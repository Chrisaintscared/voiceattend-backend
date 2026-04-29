"""
app/routes/enroll.py

Voice enrollment route.
- Model is injected from app.state (loaded once in main.py)
- Audio is normalised to WAV / 16 kHz / mono before inference
- Embedding is L2-normalised and stored as a JSON list of floats
- Duplicate enrollments are blocked (configurable)
"""

import io
import json
import asyncio
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from fastapi import APIRouter, File, HTTPException, Request, UploadFile, Depends

from app.security import get_current_user
from app.database import save_voice_profile, get_voice_profile

logger = logging.getLogger(__name__)

router = APIRouter(tags=["enroll"])

# One worker thread — keeps CPU pressure low on Render free tier.
_executor = ThreadPoolExecutor(max_workers=1)

# ── Audio constraints ────────────────────────────────────────────────────────
TARGET_SR = 16_000          # Hz  — required by ECAPA-TDNN
MIN_DURATION_SEC = 2.0      # seconds — reject clips that are too short
ENERGY_SILENCE_THRESH = 1e-4  # RMS below this → treat as silence

# ── Allowed MIME types ───────────────────────────────────────────────────────
ALLOWED_CONTENT_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/webm",
    "audio/ogg",
    "audio/mpeg",   # mp3
    "audio/mp3",
    "audio/flac",
    "audio/x-flac",
}


# ---------------------------------------------------------------------------
# Audio helpers (run inside the thread-pool, never in the async event loop)
# ---------------------------------------------------------------------------

def _load_and_preprocess(audio_bytes: bytes) -> np.ndarray:
    """
    Convert raw audio bytes → float32 numpy array at TARGET_SR, mono.

    Uses pydub for format detection/decoding (handles webm, ogg, mp3, wav …)
    then resamples with librosa if needed.
    Raises ValueError for unsupported formats or content that fails validation.
    """
    try:
        import imageio_ffmpeg
        from pydub import AudioSegment
        AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as exc:
        raise RuntimeError("pydub or imageio-ffmpeg is not installed — add both to requirements.txt") from exc

    # -- decode -----------------------------------------------------------------
    try:
        seg = AudioSegment.from_file(io.BytesIO(audio_bytes))
    except Exception as exc:
        raise ValueError(
            f"Could not decode audio. Ensure the file is a supported format "
            f"(WAV, WebM, OGG, MP3, FLAC). Detail: {exc}"
        ) from exc

    # -- normalise to mono / 16 kHz -------------------------------------------
    seg = seg.set_channels(1).set_frame_rate(TARGET_SR).set_sample_width(2)

    # -- to float32 numpy array ------------------------------------------------
    samples = np.frombuffer(seg.raw_data, dtype=np.int16).astype(np.float32)
    samples /= 32768.0          # scale to [-1, 1]

    return samples


def _validate_audio(samples: np.ndarray) -> None:
    """Raise ValueError if the clip is too short or effectively silent."""
    duration = len(samples) / TARGET_SR
    if duration < MIN_DURATION_SEC:
        raise ValueError(
            f"Audio too short ({duration:.1f}s). "
            f"Please record at least {MIN_DURATION_SEC} seconds of speech."
        )

    rms = float(np.sqrt(np.mean(samples ** 2)))
    if rms < ENERGY_SILENCE_THRESH:
        raise ValueError(
            f"Audio appears silent (RMS={rms:.2e}). "
            "Please check your microphone and try again."
        )


def _extract_and_normalise(audio_bytes: bytes, verifier) -> list[float]:
    """
    Full pipeline that runs inside the thread-pool executor:
      1. decode + resample → float32 mono array
      2. validate length & energy
      3. run ECAPA-TDNN inference
      4. L2-normalise embedding
      5. return as plain Python list of floats (JSON-safe)

    `verifier` is the SpeechBrain SpeakerRecognition object from app.state.
    """
    import torch

    # 1 + 2 — preprocess & validate
    samples = _load_and_preprocess(audio_bytes)
    _validate_audio(samples)

    # 3 — inference
    # SpeechBrain expects a (1, N) float tensor
    wav_tensor = torch.tensor(samples).unsqueeze(0)           # (1, N)
    wav_lens   = torch.tensor([1.0])                          # relative length

    with torch.no_grad():
        embedding = verifier.encode_batch(wav_tensor, wav_lens)  # (1, 1, D)

    emb_np = embedding.squeeze().cpu().numpy()                # (D,)

    # 4 — L2 normalisation
    norm = np.linalg.norm(emb_np)
    if norm < 1e-10:
        raise ValueError("Extracted embedding is a zero vector — audio may be invalid.")
    emb_np = emb_np / norm

    # 5 — plain list for JSON storage
    return emb_np.tolist()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/enroll-voice")
async def enroll_voice(
    request: Request,
    voice: UploadFile = File(...),
    user=Depends(get_current_user),
):
    # ── Auth guard ────────────────────────────────────────────────────────────
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Only students can enroll voice.")

    # ── Model guard ───────────────────────────────────────────────────────────
    verifier = getattr(request.app.state, "verifier", None)
    if verifier is None:
        raise HTTPException(
            status_code=503,
            detail="Speaker-verification model is not loaded. Try again in a few seconds.",
        )

    # ── MIME type check ───────────────────────────────────────────────────────
    content_type = (voice.content_type or "").lower().split(";")[0].strip()
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported audio format '{content_type}'. "
                f"Accepted: WAV, WebM, OGG, MP3, FLAC."
            ),
        )

    # ── Read bytes ────────────────────────────────────────────────────────────
    audio_bytes = await voice.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio file is empty.")

    # ── Duplicate enrollment check ────────────────────────────────────────────
    existing = get_voice_profile(user["id"])
    if existing is not None:
        # Change to `pass` here if you want silent overwrite instead of blocking.
        raise HTTPException(
            status_code=409,
            detail=(
                "A voice profile already exists for this account. "
                "Contact an admin to re-enroll."
            ),
        )

    # ── Inference (in thread-pool, with timeout) ──────────────────────────────
    try:
        loop = asyncio.get_event_loop()
        embedding: list[float] = await asyncio.wait_for(
            loop.run_in_executor(
                _executor,
                _extract_and_normalise,
                audio_bytes,
                verifier,           # ← injected from app.state, NOT reloaded
            ),
            timeout=30.0,
        )
    except asyncio.TimeoutError:
        logger.error("Voice embedding timed out for user %s", user["id"])
        raise HTTPException(
            status_code=504,
            detail="Voice processing timed out. Please speak for 3–5 seconds and try again.",
        )
    except ValueError as exc:
        logger.warning("Voice validation failed for user %s: %s", user["id"], exc)
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error(
            "Unexpected error during enrollment for user %s:\n%s",
            user["id"],
            traceback.format_exc(),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Voice processing failed unexpectedly: {exc}",
        )

    # ── Validate shape before DB write ────────────────────────────────────────
    if not isinstance(embedding, list) or len(embedding) < 64:
        raise HTTPException(
            status_code=500,
            detail=f"Embedding has unexpected shape ({len(embedding)}). Enrollment aborted.",
        )

    # ── Persist ───────────────────────────────────────────────────────────────
    try:
        save_voice_profile(user["id"], json.dumps(embedding))
    except Exception as exc:
        logger.error("DB write failed for user %s: %s", user["id"], exc)
        raise HTTPException(status_code=500, detail=f"Failed to save voice profile: {exc}")

    logger.info("Voice enrolled for user %s (embedding_size=%d)", user["id"], len(embedding))

    return {
        "message": "Voice enrolled successfully.",
        "user_id": user["id"],
        "user_name": user["name"],
        "embedding_size": len(embedding),   # useful for debugging
    }


@router.get("/enroll-status")
def enroll_status(
    request: Request,
    user=Depends(get_current_user),
):
    profile = get_voice_profile(user["id"])
    model_ready = getattr(request.app.state, "verifier", None) is not None
    return {
        "enrolled": profile is not None,
        "user_id": user["id"],
        "model_ready": model_ready,
    }
