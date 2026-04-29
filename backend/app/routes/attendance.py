"""
app/routes/attendance.py

Attendance check-in route with REAL speaker verification.
- Shared model injected from app.state (never reloaded here)
- Same audio preprocessing pipeline as enroll.py
- Cosine similarity threshold gates attendance marking
- save_attendance() is ONLY called after successful verification
"""

import io
import asyncio
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from fastapi import APIRouter, File, HTTPException, Request, UploadFile, Depends

from app.database import get_all_logs, get_logs_by_user, save_attendance, get_voice_profile
from app.security import get_current_user

logger = logging.getLogger(__name__)

# No prefix here — /attendance prefix is set in main.py
router = APIRouter()

# One worker thread — mirrors enroll.py, keeps Render free tier stable
_executor = ThreadPoolExecutor(max_workers=1)

# ── Verification config ──────────────────────────────────────────────────────
SIMILARITY_THRESHOLD = 0.75   # cosine similarity — tune as needed
TARGET_SR            = 16_000 # Hz  — must match enroll.py
MIN_DURATION_SEC     = 2.0    # seconds
ENERGY_SILENCE_THRESH = 1e-4  # RMS floor

# ── Allowed MIME types (mirrors enroll.py) ───────────────────────────────────
ALLOWED_CONTENT_TYPES = {
    "audio/wav", "audio/x-wav", "audio/wave",
    "audio/webm", "audio/ogg",
    "audio/mpeg", "audio/mp3",
    "audio/flac", "audio/x-flac",
}


# ---------------------------------------------------------------------------
# Audio helpers — executed inside thread-pool, never in the async event loop
# ---------------------------------------------------------------------------

def _load_and_preprocess(audio_bytes: bytes) -> np.ndarray:
    """
    Decode raw audio bytes → float32 mono array at 16 kHz.
    Identical pipeline to enroll.py so embeddings are comparable.
    """
    try:
        import imageio_ffmpeg
        from pydub import AudioSegment
        AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as exc:
        raise RuntimeError("pydub or imageio-ffmpeg is not installed — add both to requirements.txt") from exc

    try:
        seg = AudioSegment.from_file(io.BytesIO(audio_bytes))
    except Exception as exc:
        raise ValueError(
            f"Could not decode audio. Supported formats: WAV, WebM, OGG, MP3, FLAC. "
            f"Detail: {exc}"
        ) from exc

    seg     = seg.set_channels(1).set_frame_rate(TARGET_SR).set_sample_width(2)
    samples = np.frombuffer(seg.raw_data, dtype=np.int16).astype(np.float32)
    samples /= 32768.0   # scale to [-1, 1]
    return samples


def _validate_audio(samples: np.ndarray) -> None:
    """Reject clips that are too short or effectively silent."""
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


def _extract_embedding(audio_bytes: bytes, verifier) -> np.ndarray:
    """
    Full inference pipeline (runs in thread-pool):
      1. Decode + resample → float32 mono array
      2. Validate length & energy
      3. ECAPA-TDNN inference via shared verifier
      4. L2-normalise → unit vector ready for cosine comparison

    Returns a 1-D float32 numpy array.
    """
    import torch

    samples = _load_and_preprocess(audio_bytes)
    _validate_audio(samples)

    wav_tensor = torch.tensor(samples).unsqueeze(0)  # (1, N)
    wav_lens   = torch.tensor([1.0])

    with torch.no_grad():
        embedding = verifier.encode_batch(wav_tensor, wav_lens)  # (1, 1, D)

    emb_np = embedding.squeeze().cpu().numpy()       # (D,)

    norm = np.linalg.norm(emb_np)
    if norm < 1e-10:
        raise ValueError("Extracted embedding is a zero vector — audio may be invalid.")

    return emb_np / norm                              # L2-normalised unit vector


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Cosine similarity between two L2-normalised unit vectors.
    Both inputs are expected to already be unit vectors (norm ≈ 1),
    so this reduces to a dot product — fast and numerically stable.
    """
    return float(np.dot(a, b))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/test")
def test():
    return {"status": "ok", "message": "Attendance route is reachable."}


@router.post("/mark")
async def mark_attendance(
    request: Request,
    audio: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """
    Voice-verified attendance check-in.

    Pipeline:
      1. Guard: model loaded?
      2. Guard: voice enrolled?
      3. MIME type check
      4. Read audio bytes
      5. Extract & normalise embedding (thread-pool)
      6. Load stored embedding, re-normalise defensively
      7. Cosine similarity → accept / reject
      8. save_attendance() ONLY on accept
    """

    # ── 1. Model guard ────────────────────────────────────────────────────────
    verifier = getattr(request.app.state, "verifier", None)
    if verifier is None:
        raise HTTPException(
            status_code=503,
            detail="Speaker-verification model is not ready. Please try again shortly.",
        )

    # ── 2. Enrollment guard ───────────────────────────────────────────────────
    stored_profile = get_voice_profile(user["id"])
    if stored_profile is None:
        raise HTTPException(
            status_code=400,
            detail="Voice not enrolled. Please complete voice enrollment first.",
        )

    # ── 3. MIME type check ────────────────────────────────────────────────────
    content_type = (audio.content_type or "").lower().split(";")[0].strip()
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported audio format '{content_type}'. "
                "Accepted: WAV, WebM, OGG, MP3, FLAC."
            ),
        )

    # ── 4. Read bytes ─────────────────────────────────────────────────────────
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio file is empty.")

    # ── 5. Extract live embedding (non-blocking) ──────────────────────────────
    try:
        loop = asyncio.get_event_loop()
        live_emb: np.ndarray = await asyncio.wait_for(
            loop.run_in_executor(
                _executor,
                _extract_embedding,
                audio_bytes,
                verifier,          # ← injected from app.state, NOT reloaded
            ),
            timeout=30.0,
        )
    except asyncio.TimeoutError:
        logger.error("Embedding extraction timed out for user %s", user["id"])
        raise HTTPException(
            status_code=504,
            detail="Voice processing timed out. Please speak for 3–5 seconds and retry.",
        )
    except ValueError as exc:
        logger.warning("Audio validation failed for user %s: %s", user["id"], exc)
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error(
            "Unexpected error during embedding for user %s:\n%s",
            user["id"],
            traceback.format_exc(),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Voice processing failed unexpectedly: {exc}",
        )

    # ── 6. Load & re-normalise stored embedding ───────────────────────────────
    # get_voice_profile() returns a dict with embedding as List[float].
    # No json.loads() needed — the DB layer handles deserialisation.
    try:
        stored_emb  = np.array(stored_profile["embedding"], dtype=np.float32)
        stored_norm = np.linalg.norm(stored_emb)
        if stored_norm > 1e-10:
            stored_emb = stored_emb / stored_norm          # defensive re-normalise
    except Exception as exc:
        logger.error("Failed to load stored embedding for user %s: %s", user["id"], exc)
        raise HTTPException(
            status_code=500,
            detail="Stored voice profile is corrupt. Please re-enroll.",
        )

    # ── 7. Cosine similarity ──────────────────────────────────────────────────
    similarity = _cosine_similarity(live_emb, stored_emb)

    logger.info(
        "Verification for user %s | similarity=%.4f | threshold=%.2f | "
        "live_emb_size=%d | stored_emb_size=%d",
        user["id"], similarity, SIMILARITY_THRESHOLD,
        len(live_emb), len(stored_emb),
    )
    # Also print for Render log stream (visible without a logging config)
    print(
        f"[ATTENDANCE] user={user['id']} similarity={similarity:.4f} "
        f"live_size={len(live_emb)} stored_size={len(stored_emb)}"
    )

    if similarity < SIMILARITY_THRESHOLD:
        logger.warning(
            "Voice not recognised for user %s (similarity=%.4f)", user["id"], similarity
        )
        raise HTTPException(
            status_code=401,
            detail=(
                f"Voice not recognised (similarity={similarity:.4f}, "
                f"required≥{SIMILARITY_THRESHOLD}). Please try again."
            ),
        )

    # ── 8. Mark attendance ONLY after successful verification ─────────────────
    try:
        log = save_attendance(user["name"])
    except Exception as exc:
        logger.error("Failed to save attendance for user %s: %s", user["id"], exc)
        raise HTTPException(status_code=500, detail=f"Failed to record attendance: {exc}")

    logger.info("Attendance marked for user %s (similarity=%.4f)", user["id"], similarity)

    return {
        "status": "success",
        "user_name": user["name"],
        "confidence": round(similarity, 4),   # real score, not hardcoded 99
        "log": log,
    }


# ---------------------------------------------------------------------------
# Log endpoints
# ---------------------------------------------------------------------------

@router.get("/logs")
def logs():
    return {"logs": get_all_logs()}


@router.get("/logs/{user_name}")
def user_logs(user_name: str):
    return {
        "user_name": user_name,
        "logs": get_logs_by_user(user_name),
    }
