import io
import asyncio
import logging
import traceback
import gc
import ctypes
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import torch
from fastapi import APIRouter, File, HTTPException, Request, UploadFile, Depends

from app.database import get_all_logs, get_logs_by_user, save_attendance, get_voice_profile
from app.security import get_current_user

logger = logging.getLogger(__name__)

# ── Router & Execution ──────────────────────────────────────────────────────
router = APIRouter()
_executor = ThreadPoolExecutor(max_workers=1)

# ── Verification Config ──────────────────────────────────────────────────────
SIMILARITY_THRESHOLD = 0.85
TARGET_SR            = 16_000
MIN_DURATION_SEC     = 2.0
ENERGY_SILENCE_THRESH = 1e-4

ALLOWED_CONTENT_TYPES = {
    "audio/wav", "audio/x-wav", "audio/wave",
    "audio/webm", "audio/ogg",
    "audio/mpeg", "audio/mp3",
    "audio/flac", "audio/x-flac",
}

# ── Memory Helper ──────────────────────────────────────────────────────────
def trim_memory():
    """Explicitly tell the OS to reclaim memory from the Python process."""
    try:
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
    except Exception:
        pass

# ── Audio Processing Helpers ───────────────────────────────────────────────

def _load_and_preprocess(audio_bytes: bytes) -> np.ndarray:
    try:
        import imageio_ffmpeg
        from pydub import AudioSegment
        AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()
        
        seg = AudioSegment.from_file(io.BytesIO(audio_bytes))
        seg = seg.set_channels(1).set_frame_rate(TARGET_SR).set_sample_width(2)
        
        samples = np.frombuffer(seg.raw_data, dtype=np.int16).astype(np.float32)
        samples /= 32768.0
        return samples
    except Exception as exc:
        raise ValueError(f"Could not decode audio: {exc}")

def _extract_embedding(audio_bytes: bytes, verifier) -> np.ndarray:
    samples = _load_and_preprocess(audio_bytes)
    
    # Validate length
    duration = len(samples) / TARGET_SR
    if duration < MIN_DURATION_SEC:
        raise ValueError(f"Audio too short ({duration:.1f}s). Need at least {MIN_DURATION_SEC}s.")

    # Convert to Tensor for SpeechBrain/Torch
    wav_tensor = torch.tensor(samples).unsqueeze(0)
    wav_lens = torch.tensor([1.0])

    with torch.no_grad():
        embedding = verifier.encode_batch(wav_tensor, wav_lens)

    emb_np = embedding.squeeze().cpu().numpy()
    
    # L2 Normalization
    norm = np.linalg.norm(emb_np)
    if norm < 1e-10:
        raise ValueError("Invalid audio signal (silent or zero-vector).")
    
    return emb_np / norm

def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))

# ── Routes ─────────────────────────────────────────────────────────────────

@router.get("/test")
def test():
    return {"status": "ok", "message": "Attendance route is reachable."}

@router.post("/mark")
async def mark_attendance(
    request: Request,
    audio: UploadFile = File(...),
    user=Depends(get_current_user),
):
    audio_bytes = None
    try:
        # 1. Model Guard
        verifier = getattr(request.app.state, "verifier", None)
        if verifier is None:
            raise HTTPException(status_code=503, detail="Speaker model is warming up...")

        # 2. Enrollment Guard
        stored_profile = get_voice_profile(user["id"])
        if not stored_profile:
            raise HTTPException(status_code=400, detail="Voice not enrolled.")

        # 3. Read Audio Data
        audio_bytes = await audio.read()
        
        # 4. Extract Embedding (Runs in ThreadPool to keep FastAPI responsive)
        loop = asyncio.get_event_loop()
        live_emb = await asyncio.wait_for(
            loop.run_in_executor(_executor, _extract_embedding, audio_bytes, verifier),
            timeout=25.0
        )

        # 5. Calculate Similarity
        stored_emb = np.array(stored_profile["embedding"], dtype=np.float32)
        similarity = _cosine_similarity(live_emb, stored_emb)

        if similarity < SIMILARITY_THRESHOLD:
            logger.warning(f"Voice mismatch for {user['id']} (Score: {similarity:.4f})")
            raise HTTPException(
                status_code=401, 
                detail=f"Voice mismatch (Score: {similarity:.4f})"
            )

        # 6. Success
        attendance_log = save_attendance(user["name"])
        return {
            "status": "success",
            "confidence": round(similarity, 4),
            "log": attendance_log
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

    finally:
        # 🧹 CRITICAL CLEANUP: Force Render to reclaim RAM
        del audio_bytes
        gc.collect()
        trim_memory()
        logger.info("RAM cleanup complete after request.")

@router.get("/logs")
def logs():
    return {"logs": get_all_logs()}

@router.get("/logs/{user_name}")
def user_logs(user_name: str):
    return {"user_name": user_name, "logs": get_logs_by_user(user_name)}
