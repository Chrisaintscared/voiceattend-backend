"""
VoiceAttend AI - Lightweight Voice Recognition Service
Uses MFCC features instead of resemblyzer for fast CPU inference.
"""
import os
import json
import tempfile
import numpy as np
from app.config import settings


def extract_voice_embedding(audio_bytes: bytes) -> list:
    import soundfile as sf
    from scipy.signal import resample_poly
    from scipy.fftpack import dct
    from math import gcd

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        wav, sr = sf.read(tmp_path, dtype="float32")

        # Stereo to mono
        if wav.ndim > 1:
            wav = wav.mean(axis=1)

        # Resample to 16kHz
        target_sr = 16000
        if sr != target_sr:
            divisor = gcd(int(sr), target_sr)
            wav = resample_poly(wav, target_sr // divisor, sr // divisor)
            wav = wav.astype(np.float32)

        if len(wav) < target_sr:
            raise ValueError("Audio too short — speak for at least 1 second")

        # Normalize
        wav = wav / (np.max(np.abs(wav)) + 1e-9)

        # Extract MFCC embedding (fast, no torch needed)
        embedding = _extract_mfcc_embedding(wav, target_sr)
        return embedding.tolist()

    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _extract_mfcc_embedding(wav: np.ndarray, sr: int, n_mfcc: int = 64) -> np.ndarray:
    """Extract a fixed-size MFCC-based speaker embedding."""
    frame_length = int(sr * 0.025)  # 25ms
    hop_length   = int(sr * 0.010)  # 10ms
    n_fft        = 512
    n_mels       = 40

    # Pre-emphasis
    wav = np.append(wav[0], wav[1:] - 0.97 * wav[:-1])

    # Framing
    frames = _frame_signal(wav, frame_length, hop_length)

    # Hamming window
    frames *= np.hamming(frame_length)

    # Power spectrum
    mag = np.fft.rfft(frames, n=n_fft)
    power = (np.abs(mag) ** 2) / n_fft

    # Mel filterbank
    mel_filters = _mel_filterbank(sr, n_fft, n_mels)
    mel_energy = np.dot(power, mel_filters.T)
    mel_energy = np.where(mel_energy == 0, np.finfo(float).eps, mel_energy)
    log_mel = np.log(mel_energy)

    # DCT to get MFCCs
    mfcc = dct(log_mel, type=2, axis=1, norm="ortho")[:, :n_mfcc]

    # Speaker embedding = mean + std across frames (fixed size: n_mfcc * 2)
    embedding = np.concatenate([mfcc.mean(axis=0), mfcc.std(axis=0)])

    # L2 normalize
    embedding = embedding / (np.linalg.norm(embedding) + 1e-9)
    return embedding.astype(np.float32)


def _frame_signal(signal, frame_length, hop_length):
    num_frames = 1 + (len(signal) - frame_length) // hop_length
    indices = (
        np.arange(frame_length)[None, :] +
        np.arange(num_frames)[:, None] * hop_length
    )
    return signal[indices]


def _mel_filterbank(sr, n_fft, n_mels, fmin=0.0, fmax=None):
    if fmax is None:
        fmax = sr / 2.0
    freqs = np.linspace(0, sr / 2, n_fft // 2 + 1)

    def hz_to_mel(f): return 2595 * np.log10(1 + f / 700)
    def mel_to_hz(m): return 700 * (10 ** (m / 2595) - 1)

    mel_min = hz_to_mel(fmin)
    mel_max = hz_to_mel(fmax)
    mel_points = np.linspace(mel_min, mel_max, n_mels + 2)
    hz_points = mel_to_hz(mel_points)

    bins = np.floor((n_fft + 1) * hz_points / sr).astype(int)
    filters = np.zeros((n_mels, n_fft // 2 + 1))

    for m in range(1, n_mels + 1):
        f_left, f_center, f_right = bins[m - 1], bins[m], bins[m + 1]
        for k in range(f_left, f_center):
            if f_center != f_left:
                filters[m - 1, k] = (k - f_left) / (f_center - f_left)
        for k in range(f_center, f_right):
            if f_right != f_center:
                filters[m - 1, k] = (f_right - k) / (f_right - f_center)

    return filters


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
