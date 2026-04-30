import asyncio
import ctypes
import gc
import io
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import torch
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.database import get_voice_profile, save_voice_profile
from app.security import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["enroll"])

_executor = ThreadPoolExecutor(max_workers=1)

TARGET_SR = 16_000
ENERGY_SILENCE_THRESH = 0.005


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def trim_memory():
    try:
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
    except Exception:
        pass


def _extract_and_normalise(audio_bytes: bytes, verifier) -> list:
    from pydub import AudioSegment
    import shutil

    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        AudioSegment.converter = ffmpeg_path
    else:
        import imageio_ffmpeg
        AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()

    seg = AudioSegment.from_file(io.BytesIO(audio_bytes))
    seg = seg.set_channels(1).set_frame_rate(TARGET_SR).set_sample_width(2)
    samples = np.frombuffer(seg.raw_data, dtype=np.int16).astype(np.float32) / 32768.0

    rms = float(np.sqrt(np.mean(samples ** 2)))
    if rms < ENERGY_SILENCE_THRESH:
        raise ValueError("Audio too quiet. Please speak more clearly.")

    wav_tensor = torch.tensor(samples).unsqueeze(0)
    with torch.no_grad():
        embedding = verifier.encode_batch(wav_tensor, torch.tensor([1.0]))

    emb_np = embedding.squeeze().cpu().numpy()
    norm = np.linalg.norm(emb_np)
    if norm == 0:
        raise ValueError("Could not extract a valid voice embedding.")
    return (emb_np / norm).tolist()


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/enroll-voice")
async def enroll_voice(
    voice: UploadFile = File(...),
    user=Depends(get_current_user),
):
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Only students can enroll a voice profile")

    if get_voice_profile(user["id"]):
        raise HTTPException(status_code=409, detail="Voice profile already exists")

    verifier = None
    try:
        gc.collect()
        trim_memory()

        from speechbrain.inference.speaker import SpeakerRecognition

        verifier = SpeakerRecognition.from_hparams(
            source="speechbrain/spkrec-xvect-voxceleb",
            savedir="pretrained_models/spkrec-xvect",
            run_opts={"device": "cpu"},
        )

        audio_bytes = await voice.read()
        loop = asyncio.get_event_loop()

        try:
            embedding = await asyncio.wait_for(
                loop.run_in_executor(_executor, _extract_and_normalise, audio_bytes, verifier),
                timeout=45.0,
            )
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Voice processing timed out. Try again.")

        save_voice_profile(user["id"], embedding)
        return {"message": "Voice profile enrolled successfully"}

    except HTTPException:
        raise
    except Exception:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal server error during enrollment")
    finally:
        if verifier is not None:
            del verifier
        gc.collect()
        trim_memory()
