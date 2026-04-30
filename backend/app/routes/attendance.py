from __future__ import annotations

import asyncio
import gc
import io
import logging
import traceback
import ctypes
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import torch
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.database import (
    get_attendance_logs,
    get_voice_profile,
    has_attendance_today,
    is_enrolled,
    save_attendance,
)
from app.security import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["attendance"])

_executor = ThreadPoolExecutor(max_workers=1)

# ── Tuning constants ──────────────────────────────────────────────────────────
SIMILARITY_THRESHOLD = 0.72
TARGET_SR = 16_000
ENERGY_SILENCE_THRESH = 0.02

# ── Lazy-loaded model ─────────────────────────────────────────────────────────
_verifier = None
_verifier_lock = asyncio.Lock()


async def _get_verifier():
    global _verifier
    async with _verifier_lock:
        if _verifier is None:
            from speechbrain.inference.speaker import SpeakerRecognition

            logger.info("Loading SpeakerRecognition model…")
            _verifier = SpeakerRecognition.from_hparams(
                source="speechbrain/spkrec-xvect-voxceleb",
                savedir="pretrained_models/spkrec-xvect",
                run_opts={"device": "cpu"},
            )
            # Freeze model weights to save memory
            for param in _verifier.mods.parameters():
                param.requires_grad_(False)

            gc.collect()
            _trim_memory()
            logger.info("SpeakerRecognition model loaded.")
    return _verifier


# ── Helpers ───────────────────────────────────────────────────────────────────

def _trim_memory():
    try:
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
    except Exception:
        pass


def _extract_embedding(audio_bytes: bytes, verifier) -> np.ndarray:
    """Convert raw audio bytes → normalised x-vector embedding (CPU)."""
    from pydub import AudioSegment

    seg = AudioSegment.from_file(io.BytesIO(audio_bytes))
    seg = seg.set_channels(1).set_frame_rate(TARGET_SR).set_sample_width(2)
    samples = (
        np.frombuffer(seg.raw_data, dtype=np.int16).astype(np.float32) / 32768.0
    )

    rms_energy = float(np.sqrt(np.mean(samples ** 2)))
    if rms_energy < ENERGY_SILENCE_THRESH:
        raise ValueError("Audio is too quiet. Please speak more clearly.")

    # Use no_grad + explicit tensor cleanup
    tensor_input = torch.tensor(samples).unsqueeze(0)
    tensor_len = torch.tensor([1.0])
    try:
        with torch.no_grad():
            embedding = verifier.encode_batch(tensor_input, tensor_len)
        emb_np = embedding.squeeze().cpu().numpy().copy()
    finally:
        # Explicitly delete tensors to free memory immediately
        del tensor_input, tensor_len, embedding
        gc.collect()
        _trim_memory()

    norm = np.linalg.norm(emb_np)
    if norm == 0:
        raise ValueError("Could not extract a valid voice embedding.")
    return emb_np / norm


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/mark")
async def mark_attendance(
    class_id: int,
    audio: UploadFile = File(...),
    user=Depends(get_current_user),
):
    if not is_enrolled(class_id, user["id"]):
        raise HTTPException(
            status_code=403, detail="You are not enrolled in this class."
        )

    if has_attendance_today(class_id, user["id"]):
        raise HTTPException(
            status_code=409, detail="Attendance already marked for today."
        )

    stored = get_voice_profile(user["id"])
    if not stored:
        raise HTTPException(
            status_code=400,
            detail="No voice profile found. Please enroll your voice first.",
        )

    try:
        gc.collect()
        _trim_memory()

        verifier = await _get_verifier()
        audio_bytes = await audio.read()

        loop = asyncio.get_event_loop()
        try:
            live_emb = await asyncio.wait_for(
                loop.run_in_executor(
                    _executor, _extract_embedding, audio_bytes, verifier
                ),
                timeout=45.0,
            )
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504, detail="Voice processing timed out. Try again."
            )

        stored_emb = np.array(stored["embedding"])
        similarity = float(np.dot(live_emb, stored_emb))

        if similarity < SIMILARITY_THRESHOLD:
            raise HTTPException(
                status_code=401,
                detail=f"Voice not recognised (score: {similarity:.2f}). Try again.",
            )

        save_attendance(
            user_id=user["id"],
            user_name=user["name"],
            class_id=class_id,
        )

        return {"status": "success", "confidence": round(similarity * 100, 2)}

    except HTTPException:
        raise
    except Exception:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal server error.")
    finally:
        gc.collect()
        _trim_memory()


@router.get("/logs")
async def get_logs(
    class_id: int | None = None,
    user=Depends(get_current_user),
):
    try:
        logs = get_attendance_logs(user_id=user["id"], class_id=class_id)
        return {"logs": logs}
    except Exception:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Failed to load attendance logs.")


@router.get("/test")
async def test_connection():
    return {"status": "ok"}
