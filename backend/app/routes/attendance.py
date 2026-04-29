import io, asyncio, logging, traceback, gc, ctypes
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import torch
from fastapi import APIRouter, File, HTTPException, Request, UploadFile, Depends
from app.database import save_attendance, get_voice_profile
from app.security import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["attendance"])
_executor = ThreadPoolExecutor(max_workers=1)

SIMILARITY_THRESHOLD = 0.72 # Optimized for X-Vector
TARGET_SR = 16_000
ENERGY_SILENCE_THRESH = 0.005

def trim_memory():
    try:
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
    except: pass

def _extract_embedding(audio_bytes: bytes, verifier) -> np.ndarray:
    from pydub import AudioSegment
    seg = AudioSegment.from_file(io.BytesIO(audio_bytes))
    seg = seg.set_channels(1).set_frame_rate(TARGET_SR).set_sample_width(2)
    samples = np.frombuffer(seg.raw_data, dtype=np.int16).astype(np.float32) / 32768.0
    
    if float(np.sqrt(np.mean(samples**2))) < ENERGY_SILENCE_THRESH:
        raise ValueError("Silent audio.")

    with torch.no_grad():
        embedding = verifier.encode_batch(torch.tensor(samples).unsqueeze(0), torch.tensor([1.0]))
    
    emb_np = embedding.squeeze().cpu().numpy()
    return emb_np / np.linalg.norm(emb_np)

@router.post("/mark")
async def mark_attendance(audio: UploadFile = File(...), user=Depends(get_current_user)):
    verifier = None
    try:
        stored = get_voice_profile(user["id"])
        if not stored: raise HTTPException(status_code=400, detail="No profile")

        # ── PRE-LOAD CLEANUP ──
        gc.collect()
        trim_memory()

        from speechbrain.inference.speaker import SpeakerRecognition
        verifier = SpeakerRecognition.from_hparams(
            source="speechbrain/spkrec-xvect-voxceleb", # LIGHTWEIGHT MODEL
            savedir="pretrained_models/spkrec-xvect",
            run_opts={"device": "cpu"}
        )

        audio_bytes = await audio.read()
        loop = asyncio.get_event_loop()
        live_emb = await asyncio.wait_for(
            loop.run_in_executor(_executor, _extract_embedding, audio_bytes, verifier),
            timeout=45.0
        )

        similarity = float(np.dot(live_emb, np.array(stored["embedding"])))
        if similarity < SIMILARITY_THRESHOLD:
            raise HTTPException(status_code=401, detail=f"Mismatch ({similarity:.2f})")

        return {"status": "success", "score": round(similarity, 4), "log": save_attendance(user["name"])}

    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        del verifier
        gc.collect()
        trim_memory()
