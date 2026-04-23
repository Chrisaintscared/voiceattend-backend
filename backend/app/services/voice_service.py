import numpy as np
from app.config import settings

def extract_voice_embedding(audio_bytes: bytes):
    # SAFE DUMMY MODEL (prevents crashes)
    return np.random.rand(40).tolist()


def find_best_match(query_embedding, profiles):
    best = None
    best_score = -1

    for p in profiles:
        emb = eval(p["embedding"]) if isinstance(p["embedding"], str) else p["embedding"]

        score = float(np.dot(query_embedding, emb))

        if score > best_score:
            best_score = score
            best = p

    if best and best_score >= settings.voice_similarity_threshold:
        return best, best_score

    return None, best_score