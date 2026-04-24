"""
VoiceAttend AI - Voice Recognition Model
Librosa/numba are imported lazily (inside functions) to avoid
blocking Render's startup health-check with JIT compilation.
"""

import io
from app.config import settings

SAMPLE_RATE = 16_000
N_MFCC      = 40
N_FFT       = 512
HOP_LENGTH  = 160


# ── Fast dummy used until a real model is trained ──────────────────────────

def extract_voice_embedding(audio_bytes: bytes) -> list[float]:
    """Returns a random embedding. Replace with real model when ready."""
    import numpy as np          # lazy — no startup cost
    return np.random.rand(N_MFCC).tolist()


# ── Real pipeline (activates once librosa is needed) ───────────────────────

def load_audio(audio_bytes: bytes):
    import librosa              # lazy — numba JIT happens here, not at startup
    import numpy as np
    buf = io.BytesIO(audio_bytes)
    return librosa.load(buf, sr=SAMPLE_RATE, mono=True)


def extract_features(waveform, sr: int = SAMPLE_RATE):
    import librosa
    import numpy as np
    mfcc            = librosa.feature.mfcc(y=waveform, sr=sr, n_mfcc=N_MFCC,
                                            n_fft=N_FFT, hop_length=HOP_LENGTH)
    delta           = librosa.feature.delta(mfcc)
    centroid        = librosa.feature.spectral_centroid(y=waveform, sr=sr)
    zcr             = librosa.feature.zero_crossing_rate(y=waveform)
    return np.concatenate([
        mfcc.mean(1), mfcc.std(1),
        delta.mean(1), delta.std(1),
        [centroid.mean(), zcr.mean()],
    ]).astype("float32")


def process_audio(audio_bytes: bytes) -> dict:
    """Full pipeline — only call this when you have a real model."""
    import numpy as np
    waveform, sr   = load_audio(audio_bytes)
    features       = extract_features(waveform, sr)
    confidence     = float(np.random.uniform(0.70, 0.99))
    return {"user_name": "demo_user", "confidence": round(confidence, 4)}


# ── Similarity matching ─────────────────────────────────────────────────────

def find_best_match(query_embedding, profiles):
    import numpy as np
    best, best_score = None, -1
    for p in profiles:
        emb   = eval(p["embedding"]) if isinstance(p["embedding"], str) else p["embedding"]
        score = float(np.dot(query_embedding, emb))
        if score > best_score:
            best_score, best = score, p
    if best and best_score >= settings.voice_similarity_threshold:
        return best, best_score
    return None, best_score
