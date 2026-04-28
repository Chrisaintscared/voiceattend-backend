"""
VoiceAttend AI - Real Voice Recognition Service
Uses resemblyzer for speaker embedding extraction.
"""

import os
import json
import tempfile
import numpy as np

from app.config import settings

_encoder = None

def _get_encoder():
    global _encoder
    if _encoder is None:
        print("🔊 Loading voice encoder...")
        from resemblyzer import VoiceEncoder
        _encoder = VoiceEncoder(device="cpu")
        print("✅ Voice encoder loaded")
    return _encoder


def extract_voice_embedding(audio_bytes: bytes) -> list:
    import librosa

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        # Load and resample to 16kHz mono
        wav, sr = librosa.load(tmp_path, sr=16000, mono=True)

        if len(wav) < 16000:
            raise ValueError("Audio too short — speak for at least 1 second")

        # Normalize
        wav = wav / (np.max(np.abs(wav)) + 1e-9)

        # Convert to float32
        wav = wav.astype(np.float32)

        encoder = _get_encoder()
        embedding = encoder.embed_utterance(wav)
        return embedding.tolist()

    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def find_best_match(query_embedding, profiles):
    query = np.array(query_embedding)
    query = query / (np.linalg.norm(query) + 1e-9)

    best = None
    best_score = -1

    for p in profiles:
        try:
            stored = p["embedding"]
            if isinstance(stored, str):
                stored = json.loads(stored)
            emb = np.array(stored)
            emb = emb / (np.linalg.norm(emb) + 1e-9)
            score = float(np.dot(query, emb))

            if score > best_score:
                best_score = score
                best = p

        except Exception as e:
            print(f"⚠️ Skipping profile {p.get('user_id')}: {e}")
            continue

    threshold = getattr(settings, 'voice_similarity_threshold', 0.75)

    if best and best_score >= threshold:
        return best, best_score

    return None, best_score
