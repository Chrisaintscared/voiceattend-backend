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
# TIGHTENED: Increased from 1e-4 to 5e-3 to reject low-level background hiss
ENERGY_SILENCE_THRESH = 0.005 

ALLOWED_CONTENT_TYPES = {
    "audio/wav", "audio/x-wav", "audio/wave",
    "audio/webm", "audio/ogg",
    "audio/mpeg", "audio/mp3",
    "audio/flac", "audio/x-flac",
}

def trim_memory():
    try:
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
    except Exception: pass

def _load_and_preprocess(audio_bytes: bytes) -> np.ndarray:
    try:
        import imageio_ffmpeg
        from pydub import AudioSegment
        AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()
        seg = AudioSegment.from_file(io.BytesIO(audio_bytes))
        seg = seg.set_channels(1).set_frame_rate(TARGET_SR).set_sample_width(2)
        samples = np.frombuffer(seg.raw_data, dtype=np.int16).astype(np.float32)
        return samples / 32768.0
    except Exception as exc:
        raise ValueError(f"Could not decode audio: {exc}")

def _extract_and_normalise(audio_bytes: bytes, verifier) -> list[float]:
    samples = _load_and_preprocess(audio_bytes)
    
    # ── Strict Silence Check ──
    rms = float(np.sqrt(np.mean(samples**2)))
    if rms < ENERGY_SILENCE_THRESH:
        raise ValueError(f"Audio is too quiet or silent. Please speak louder.")

    duration = len(samples) / TARGET_SR
    if duration < MIN_DURATION_SEC:
        raise ValueError(f"Audio too short ({duration:.1f}s). Need {MIN_DURATION_SEC}s.")

    wav_tensor = torch.tensor(samples).unsqueeze(0)
    wav_lens = torch.tensor([1.0])

    with torch.no_grad():
        embedding = verifier.encode_batch(wav_tensor, wav_lens)

    emb_np = embedding.squeeze().cpu().numpy()
    norm = np.linalg.norm(emb_np)
    if norm < 1e-10:
        raise ValueError("Invalid audio signal.")
    
    return (emb_np / norm).tolist()

@router.post("/enroll-voice")
async def enroll_voice(request: Request, voice: UploadFile = File(...), user=Depends(get_current_user)):
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Only students can enroll.")

    audio_bytes = None
    verifier = None

    try:
        existing = get_voice_profile(user["id"])
        if existing:
            raise HTTPException(status_code=409, detail="Voice profile already exists.")

        from speechbrain.inference.speaker import SpeakerRecognition
        logger.info("⏳ Loading model for enrollment...")
        
        verifier = SpeakerRecognition.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir="pretrained_models/spkrec-ecapa-voxceleb",
            run_opts={"device": "cpu"},
        )

        audio_bytes = await voice.read()
        loop = asyncio.get_event_loop()
        embedding = await asyncio.wait_for(
            loop.run_in_executor(_executor, _extract_and_normalise, audio_bytes, verifier),
            timeout=45.0
        )

        save_voice_profile(user["id"], embedding)
        return {"message": "Voice enrolled successfully.", "embedding_size": len(embedding)}

    except HTTPException: raise
    except Exception as e:
        logger.error(f"Enrollment error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if verifier: del verifier
        if audio_bytes: del audio_bytes
        gc.collect()
        trim_memory()
