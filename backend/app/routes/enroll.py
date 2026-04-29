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

from app.security import get_current_user
from app.database import save_voice_profile, get_voice_profile

logger = logging.getLogger(__name__)
router = APIRouter(tags=["enroll"])
_executor = ThreadPoolExecutor(max_workers=1)

# ── Config ──────────────────────────────────────────────────────────────────
TARGET_SR = 16_000
MIN_DURATION_SEC = 2.0
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

def _extract_and_normalise(audio_bytes: bytes, verifier) -> list[float]:
    samples = _load_and_preprocess(audio_bytes)
    
    # Validation
    duration = len(samples) / TARGET_SR
    if duration < MIN_DURATION_SEC:
        raise ValueError(f"Audio too short ({duration:.1f}s). Need {MIN_DURATION_SEC}s.")

    # Inference
    wav_tensor = torch.tensor(samples).unsqueeze(0)
    wav_lens = torch.tensor([1.0])

    with torch.no_grad():
        embedding = verifier.encode_batch(wav_tensor, wav_lens)

    emb_np = embedding.squeeze().cpu().numpy()
    
    # Normalisation
    norm = np.linalg.norm(emb_np)
    if norm < 1e-10:
        raise ValueError("Invalid audio signal.")
    
    return (emb_np / norm).tolist()

# ── Routes ─────────────────────────────────────────────────────────────────

@router.post("/enroll-voice")
async def enroll_voice(
    request: Request,
    voice: UploadFile = File(...),
    user=Depends(get_current_user),
):
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Only students can enroll.")

    audio_bytes = None
    verifier = None

    try:
        # 1. Check for existing profile FIRST (saves RAM if already enrolled)
        existing = get_voice_profile(user["id"])
        if existing:
            raise HTTPException(status_code=409, detail="Voice profile already exists.")

        # 2. LOAD MODEL ON-DEMAND (The RAM-saving trick)
        from speechbrain.inference.speaker import SpeakerRecognition
        logger.info("⏳ Loading ECAPA-TDNN for enrollment...")
        
        verifier = SpeakerRecognition.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir="pretrained_models/spkrec-ecapa-voxceleb",
            run_opts={"device": "cpu"},
        )

        # 3. Read Audio
        audio_bytes = await voice.read()
        
        # 4. Extract (Threaded)
        loop = asyncio.get_event_loop()
        embedding = await asyncio.wait_for(
            loop.run_in_executor(_executor, _extract_and_normalise, audio_bytes, verifier),
            timeout=45.0
        )

        # 5. Save to DB
        save_voice_profile(user["id"], embedding)
        return {"message": "Voice enrolled successfully.", "embedding_size": len(embedding)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Enrollment error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # 🧹 AGGRESSIVE RAM RECLAMATION
        del verifier
        del audio_bytes
        gc.collect()
        trim_memory()
        logger.info("✅ Enrollment RAM cleared.")

@router.get("/enroll-status")
def enroll_status(user=Depends(get_current_user)):
    profile = get_voice_profile(user["id"])
    return {
        "enrolled": profile is not None,
        "user_id": user["id"]
    }
