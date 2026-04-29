import io, asyncio, logging, traceback, gc, ctypes
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import torch
from fastapi import APIRouter, File, HTTPException, Request, UploadFile, Depends
from app.security import get_current_user
from app.database import save_voice_profile, get_voice_profile

logger = logging.getLogger(__name__)
router = APIRouter(tags=["enroll"])
_executor = ThreadPoolExecutor(max_workers=1)

TARGET_SR = 16_000
MIN_DURATION_SEC = 2.0
ENERGY_SILENCE_THRESH = 0.005 

def trim_memory():
    try:
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
    except: pass

def _extract_and_normalise(audio_bytes: bytes, verifier) -> list[float]:
    import imageio_ffmpeg
    from pydub import AudioSegment
    AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()
    
    seg = AudioSegment.from_file(io.BytesIO(audio_bytes))
    seg = seg.set_channels(1).set_frame_rate(TARGET_SR).set_sample_width(2)
    samples = np.frombuffer(seg.raw_data, dtype=np.int16).astype(np.float32) / 32768.0
    
    if float(np.sqrt(np.mean(samples**2))) < ENERGY_SILENCE_THRESH:
        raise ValueError("Audio too quiet.")

    wav_tensor = torch.tensor(samples).unsqueeze(0)
    with torch.no_grad():
        embedding = verifier.encode_batch(wav_tensor, torch.tensor([1.0]))

    emb_np = embedding.squeeze().cpu().numpy()
    return (emb_np / np.linalg.norm(emb_np)).tolist()

@router.post("/enroll-voice")
async def enroll_voice(voice: UploadFile = File(...), user=Depends(get_current_user)):
    if user["role"] != "student": raise HTTPException(status_code=403)
    
    verifier = None
    try:
        if get_voice_profile(user["id"]): raise HTTPException(status_code=409, detail="Already exists")

        # ── PRE-LOAD CLEANUP ──
        gc.collect()
        trim_memory()

        from speechbrain.inference.speaker import SpeakerRecognition
        verifier = SpeakerRecognition.from_hparams(
            source="speechbrain/spkrec-xvect-voxceleb", # LIGHTWEIGHT MODEL
            savedir="pretrained_models/spkrec-xvect",
            run_opts={"device": "cpu"}
        )

        audio_bytes = await voice.read()
        loop = asyncio.get_event_loop()
        embedding = await asyncio.wait_for(
            loop.run_in_executor(_executor, _extract_and_normalise, audio_bytes, verifier),
            timeout=45.0
        )

        save_voice_profile(user["id"], embedding)
        return {"message": "Success"}

    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        del verifier
        gc.collect()
        trim_memory()
