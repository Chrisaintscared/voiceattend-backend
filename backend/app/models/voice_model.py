import io
import numpy as np
from app.config import settings

SAMPLE_RATE = 16_000
N_MFCC = 40

def extract_voice_embedding(audio_bytes: bytes) -> list[float]:
    """Dummy embedding — replace with real model when ready."""
    return np.random.rand(N_MFCC).tolist()

def find_best_match(query_embedding, profiles):
    best, best_score = None, -1
    for p in profiles:
        emb = eval(p["embedding"]) if isinstance(p["embedding"], str) else p["embedding"]
        score = float(np.dot(query_embedding, emb))
        if score > best_score:
            best_score, best = score, p
    if best and best_score >= settings.voice_similarity_threshold:
        return best, best_score
    return None, best_score

def process_audio(audio_bytes: bytes) -> dict:
    """Placeholder pipeline."""
    embedding = extract_voice_embedding(audio_bytes)
    return {"user_name": "demo_user", "confidence": round(float(np.random.uniform(0.70, 0.99)), 4)}
