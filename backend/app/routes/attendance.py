import io, asyncio, logging, traceback, gc, ctypes
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import torch
from fastapi import APIRouter, File, HTTPException, UploadFile, Depends
from app.database import save_attendance, get_voice_profile
from app.security import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["attendance"])
_executor = ThreadPoolExecutor(max_workers=1)

SIMILARITY_THRESHOLD = 0.72 
TARGET_SR = 16_000
# Increased threshold: 0.02 is better for filtering room noise/static
ENERGY_SILENCE_THRESH = 0.02 

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
    
    # Calculate Root Mean Square energy
    rms_energy = float(np.sqrt(np.mean(samples**2)))
    if rms_energy < ENERGY_SILENCE_THRESH:
        raise ValueError("Audio is too quiet. Please speak more clearly.")

    with torch.no_grad():
        embedding = verifier.encode_batch(torch.tensor(samples).unsqueeze(0), torch.tensor([1.0]))
    
    emb_np = embedding.squeeze().cpu().numpy()
    return emb_np / np.linalg.norm(emb_np)

@router.post("/mark")
async def mark_attendance(
    class_id: int, 
    audio: UploadFile = File(...), 
    user=Depends(get_current_user)
):
    verifier = None
    try:
        stored = get_voice_profile(user["id"])
        if not stored: 
            raise HTTPException(status_code=400, detail="Voice profile not found. Please enroll first.")

        gc.collect()
        trim_memory()

        from speechbrain.inference.speaker import SpeakerRecognition
        verifier = SpeakerRecognition.from_hparams(
            source="speechbrain/spkrec-xvect-voxceleb",
            savedir="pretrained_models/spkrec-xvect",
            run_opts={"device": "cpu"}
        )

        audio_bytes = await audio.read()
        loop = asyncio.get_event_loop()
        
        try:
            live_emb = await asyncio.wait_for(
                loop.run_in_executor(_executor, _extract_embedding, audio_bytes, verifier),
                timeout=45.0
            )
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))

        similarity = float(np.dot(live_emb, np.array(stored["embedding"])))
        
        if similarity < SIMILARITY_THRESHOLD:
            # We return a 401 but include the score for debugging
            raise HTTPException(status_code=401, detail=f"Voice mismatch (Confidence: {similarity:.2f})")

        # Pass both class_id and user info to the database
        result = save_attendance(user_id=user["id"], user_name=user["name"], class_id=class_id)

        return {
            "status": "success", 
            "confidence": round(similarity * 100, 2), 
            "message": "Attendance marked successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        if verifier: del verifier
        gc.collect()
        trim_memory()
