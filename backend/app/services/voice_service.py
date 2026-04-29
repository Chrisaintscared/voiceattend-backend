"""
app/services/voice_service.py

Real speaker-verification service for VoiceAttend AI.

Design rules:
  - NO model loading here. The SpeechBrain ECAPA-TDNN model is loaded
    once in main.py and injected via app.state into every call.
  - All heavy imports (torch, pydub) are at module level so the
    interpreter pays the import cost once, not per request.
  - This module is pure computation — no FastAPI, no DB, no I/O side effects.
  - Both enroll.py and attendance.py call extract_voice_embedding() with the
    same arguments, guaranteeing identical preprocessing on both sides.
"""

import io
import logging

import numpy as np

# Heavy imports at module level — Render pays this cost once at cold start,
# not on every request.
try:
    import torch
except ImportError as _e:
    raise ImportError("torch is required: pip install torch") from _e

try:
    from pydub import AudioSegment
except ImportError as _e:
    raise ImportError(
        "pydub is required: pip install pydub  (also add ffmpeg to packages.txt on Render)"
    ) from _e

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — kept as module-level constants so callers can inspect them
# ---------------------------------------------------------------------------

TARGET_SR             = 16_000   # Hz  — ECAPA-TDNN is trained at 16 kHz
MIN_DURATION_SEC      = 2.0      # seconds — clips shorter than this are rejected
ENERGY_SILENCE_THRESH = 1e-4     # RMS floor — below this we treat audio as silent

# Accepted pydub format hints (derived from common MIME type suffixes).
# pydub auto-detects format from the byte stream, but we keep this for
# documentation / future explicit-format calls.
SUPPORTED_FORMATS = {"wav", "webm", "ogg", "mp3", "flac"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _decode_to_samples(audio_bytes: bytes) -> np.ndarray:
    """
    Decode raw audio bytes (any pydub-supported container) into a
    float32 numpy array normalised to [-1, 1] at TARGET_SR, mono.

    Raises
    ------
    ValueError
        If the bytes cannot be decoded or represent an unsupported format.
    """
    if not audio_bytes:
        raise ValueError("audio_bytes is empty — nothing to decode.")

    try:
        seg = AudioSegment.from_file(io.BytesIO(audio_bytes))
    except Exception as exc:
        raise ValueError(
            f"Failed to decode audio. Ensure the file is WAV, WebM, OGG, MP3, or FLAC. "
            f"Detail: {exc}"
        ) from exc

    # Force: mono, 16 kHz, 16-bit PCM
    seg = (
        seg
        .set_channels(1)
        .set_frame_rate(TARGET_SR)
        .set_sample_width(2)          # 2 bytes = 16-bit
    )

    samples = np.frombuffer(seg.raw_data, dtype=np.int16).astype(np.float32)
    samples /= 32_768.0               # scale PCM int16 → float32 [-1, 1]
    return samples


def _validate_samples(samples: np.ndarray) -> None:
    """
    Reject audio that is too short or effectively silent.

    Raises
    ------
    ValueError
        With a user-readable description of what failed.
    """
    duration_sec = len(samples) / TARGET_SR

    if duration_sec < MIN_DURATION_SEC:
        raise ValueError(
            f"Audio too short ({duration_sec:.2f}s). "
            f"Please record at least {MIN_DURATION_SEC:.0f} seconds of clear speech."
        )

    rms = float(np.sqrt(np.mean(samples ** 2)))
    if rms < ENERGY_SILENCE_THRESH:
        raise ValueError(
            f"Audio appears to be silent (RMS energy = {rms:.2e}). "
            "Please check your microphone level and try again."
        )

    logger.debug(
        "Audio validated: duration=%.2fs  rms=%.4f  samples=%d",
        duration_sec, rms, len(samples),
    )


def _l2_normalise(vector: np.ndarray) -> np.ndarray:
    """
    Return the L2-normalised (unit) version of `vector`.

    Raises
    ------
    ValueError
        If the vector is a zero vector (degenerate embedding).
    """
    norm = np.linalg.norm(vector)
    if norm < 1e-10:
        raise ValueError(
            "Embedding is a zero vector — the audio may be corrupt or too noisy."
        )
    return vector / norm


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_voice_embedding(audio_bytes: bytes, model) -> list[float]:
    """
    Extract an L2-normalised speaker embedding from raw audio bytes.

    Parameters
    ----------
    audio_bytes : bytes
        Raw audio file content (WAV, WebM, OGG, MP3, or FLAC).
    model : SpeechBrain SpeakerRecognition
        The ECAPA-TDNN model loaded once in main.py and stored in
        ``app.state.verifier``.  This function does NOT load or cache
        any model internally.

    Returns
    -------
    list[float]
        A 1-D list of floats representing the L2-normalised speaker
        embedding (192 dimensions for ECAPA-TDNN).

    Raises
    ------
    ValueError
        For invalid, too-short, or silent audio.
    RuntimeError
        For unexpected inference failures.
    """
    if model is None:
        raise RuntimeError(
            "model is None — ensure app.state.verifier is loaded before calling "
            "extract_voice_embedding()."
        )

    # ── 1. Decode + resample ─────────────────────────────────────────────────
    samples = _decode_to_samples(audio_bytes)

    # ── 2. Validate length & energy ──────────────────────────────────────────
    _validate_samples(samples)

    # ── 3. Build tensor for ECAPA-TDNN ───────────────────────────────────────
    # encode_batch expects (batch, time) with float32 in [-1, 1]
    wav_tensor = torch.tensor(samples, dtype=torch.float32).unsqueeze(0)  # (1, N)
    wav_lens   = torch.tensor([1.0])                                       # relative lengths

    logger.debug(
        "Running inference: wav_tensor.shape=%s  duration=%.2fs",
        tuple(wav_tensor.shape), len(samples) / TARGET_SR,
    )

    # ── 4. Inference ─────────────────────────────────────────────────────────
    try:
        with torch.no_grad():
            # Returns (batch, 1, embedding_dim) — e.g. (1, 1, 192) for ECAPA
            raw_embedding = model.encode_batch(wav_tensor, wav_lens)
    except Exception as exc:
        raise RuntimeError(f"ECAPA-TDNN inference failed: {exc}") from exc

    # Squeeze to 1-D numpy array: (192,)
    emb_np = raw_embedding.squeeze().cpu().numpy().astype(np.float32)

    logger.debug("Raw embedding: shape=%s  norm=%.4f", emb_np.shape, float(np.linalg.norm(emb_np)))

    # ── 5. L2 normalise ──────────────────────────────────────────────────────
    emb_unit = _l2_normalise(emb_np)

    logger.info(
        "Embedding extracted successfully: dim=%d  norm_after=%.6f",
        len(emb_unit), float(np.linalg.norm(emb_unit)),
    )

    # ── 6. Return as plain Python list (JSON-serialisable) ───────────────────
    return emb_unit.tolist()


# ---------------------------------------------------------------------------
# NOTE: find_best_match() has been intentionally removed.
#
# Matching (cosine similarity) is performed in attendance.py so that:
#   • The threshold is configurable per route without touching this module.
#   • The service layer stays stateless and easily unit-testable.
#   • There is a single source of truth for the similarity logic.
#
# Cosine similarity between two L2-normalised vectors a and b:
#   similarity = float(np.dot(a, b))   # dot product of unit vectors = cosine
# ---------------------------------------------------------------------------
