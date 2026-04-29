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

from app.database import save_attendance, get_voice_profile, get_all_logs, get_logs_by_user
from app.security import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["attendance"])
_executor = ThreadPoolExecutor(max_workers=1)

# ── Config ──────────────────────────────────────────────────────────────────
# TIGHTENED: Increased from 0.85 to 0.90 to stop false positives
SIMILARITY_THRESHOLD = 0.90 
TARGET_SR            = 16_000
# REJECT SILENCE: Same threshold as enrollment
ENERGY_SILENCE_THRESH = 0.005

def trim_memory():
    try:
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
    except Exception: pass

def _load_and_preprocess(audio_bytes: bytes) -> np.ndarray:
    try:
        from pydub import AudioSegment
        import imageio_ffmpeg
        AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()
        seg = AudioSegment.from_file(io.BytesIO(audio_bytes))
        seg = seg.set_channels(1).set_frame_rate(TARGET_SR).set_sample_width(2)
        samples = np.frombuffer(seg.raw_data, dtype=np.int16).astype(np.float32)
        return samples / 32768.0
    except Exception as exc:
        raise ValueError(f"Could not decode audio: {exc}")

def _extract_embedding(audio_bytes: bytes, verifier) -> np.ndarray:
    samples = _load_and_preprocess(audio_bytes)
    
    # ── Silence Check ──
    rms = float(np.sqrt(np.mean(samples**2)))
    if rms < ENERGY_SILENCE_THRESH:
        raise ValueError("Audio is silent. Please speak clearly.")

    wav_tensor = torch.tensor(samples).unsqueeze(0)
    wav_lens = torch.tensor([1.0])

    with torch.no_grad():
        embedding = verifier.encode_batch(wav_tensor, wav_lens)

    emb_np = embedding.squeeze().cpu().numpy()
    return emb_np / np.linalg.norm(emb_np)

def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))

@router.post("/mark")
async def mark_attendance(request: Request, audio: UploadFile = File(...), user=Depends(get_current_user)):
    audio_bytes = None
    verifier = None
    
    try:
        stored_profile = get_voice_profile(user["id"])
        if not stored_profile:
            raise HTTPException(status_code=400, detail="Voice not enrolled.")

        from speechbrain.inference.speaker import SpeakerRecognition
        logger.info("⏳ Loading model for check-in...")
        
        verifier = SpeakerRecognition.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir="pretrained_models/spkrec-ecapa-voxceleb",
            run_opts={"device": "cpu"},
        )

        audio_bytes = await audio.read()
        loop = asyncio.get_event_loop()
        live_emb = await asyncio.wait_for(
            loop.run_in_executor(_executor, _extract_embedding, audio_bytes, verifier),
            timeout=45.0
        )

        stored_emb = np.array(stored_profile["embedding"], dtype=np.float32)
        similarity = _cosine_similarity(live_emb, stored_emb)

        if similarity < SIMILARITY_THRESHOLD:
            logger.warning(f"Mismatch for {user['id']} (Score: {similarity:.4f})")
            raise HTTPException(status_code=401, detail=f"Voice mismatch ({similarity:.4f})")

        attendance_log = save_attendance(user["name"])
        return {"status": "success", "confidence": round(similarity, 4), "log": attendance_log}

    except HTTPException: raise
    except Exception as e:
        logger.error(f"Attendance error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if verifier: del verifier
        if audio_bytes: del audio_bytes
        gc.collect()
        trim_memory()
