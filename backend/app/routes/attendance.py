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

# One worker thread to prevent CPU/RAM competition on Render
_executor = ThreadPoolExecutor(max_workers=1)

# ── Config ──────────────────────────────────────────────────────────────────
SIMILARITY_THRESHOLD = 0.85
TARGET_SR            = 16_000

# ── Memory Helper ──────────────────────────────────────────────────────────
def trim_memory():
    """Forces the Linux kernel to reclaim unused memory from the process."""
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
    """Runs inside the executor to handle heavy ML math."""
    samples = _load_and_preprocess(audio_bytes)
    
    # Inference
    wav_tensor = torch.tensor(samples).unsqueeze(0)
    wav_lens = torch.tensor([1.0])

    with torch.no_grad():
        embedding = verifier.encode_batch(wav_tensor, wav_lens)

    emb_np = embedding.squeeze().cpu().numpy()
    
    # L2 Normalisation
    norm = np.linalg.norm(emb_np)
    if norm < 1e-10:
        raise ValueError("Invalid audio signal.")
    
    return emb_np / norm

def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))

# ── Routes ─────────────────────────────────────────────────────────────────

@router.post("/mark")
async def mark_attendance(
    request: Request,
    audio: UploadFile = File(...),
    user=Depends(get_current_user),
):
    audio_bytes = None
    verifier = None
    
    try:
        # 1. Verification Guard: Check if user has a profile BEFORE loading model
        stored_profile = get_voice_profile(user["id"])
        if not stored_profile:
            raise HTTPException(status_code=400, detail="Voice not enrolled.")

        # 2. LOAD MODEL ON-DEMAND
        from speechbrain.inference.speaker import SpeakerRecognition
        logger.info("⏳ Loading ECAPA-TDNN for check-in...")
        
        verifier = SpeakerRecognition.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir="pretrained_models/spkrec-ecapa-voxceleb",
            run_opts={"device": "cpu"},
        )

        # 3. Read incoming audio
        audio_bytes = await audio.read()
        
        # 4. Extract Embedding (Offloaded to ThreadPool)
        loop = asyncio.get_event_loop()
        live_emb = await asyncio.wait_for(
            loop.run_in_executor(_executor, _extract_embedding, audio_bytes, verifier),
            timeout=45.0
        )

        # 5. Compare against stored profile
        stored_emb = np.array(stored_profile["embedding"], dtype=np.float32)
        similarity = _cosine_similarity(live_emb, stored_emb)

        if similarity < SIMILARITY_THRESHOLD:
            logger.warning(f"Mismatch for {user['id']} (Score: {similarity:.4f})")
            raise HTTPException(
                status_code=401, 
                detail=f"Voice mismatch (Score: {similarity:.4f})"
            )

        # 6. Log Success
        attendance_log = save_attendance(user["name"])
        return {
            "status": "success",
            "confidence": round(similarity, 4),
            "log": attendance_log
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Attendance error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # 🧹 AGGRESSIVE RAM RECLAMATION
        if verifier:
            del verifier
        if audio_bytes:
            del audio_bytes
        gc.collect()
        trim_memory()
        logger.info("✅ Attendance RAM cleared.")

@router.get("/logs")
def logs():
    return {"logs": get_all_logs()}

@router.get("/logs/{user_name}")
def user_logs(user_name: str):
    return {"user_name": user_name, "logs": get_logs_by_user(user_name)}
