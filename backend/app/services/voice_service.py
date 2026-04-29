"""
VoiceAttend AI — app/services/voice_service.py
================================================
Speaker-embedding extraction using SpeechBrain ECAPA-TDNN.

Architecture contract (READ BEFORE EDITING)
────────────────────────────────────────────
* This module is STATELESS. It holds no references to the ML model.
* The caller (enroll.py, attendance.py, auth.py) is responsible for
  fetching app.state.verifier and passing it as the `model` argument.
* This module NEVER accesses FastAPI's app.state, request objects, or
  any HTTP context — it is pure computation.
* This design keeps the service layer testable in isolation:
    embed = extract_voice_embedding(audio_bytes, model=mock_model)
* `model=None` is deliberately NOT used as a default — a missing model
  is a caller bug, not a graceful-degradation scenario. The caller must
  guard with HTTP 503 before calling this function.

Guaranteed output contract
──────────────────────────
* Returns a 1-D Python list[float] of length == model embedding dim (192
  for ECAPA-TDNN on VoxCeleb).
* The vector is L2-normalised (unit length) so callers can compute cosine
  similarity as a plain dot product:
      similarity = float(np.dot(a, b))
* Raises ValueError for bad/short/silent audio (caller → HTTP 422).
* Raises RuntimeError for inference failures (caller → HTTP 422/503).
* Never raises anything else — all exceptions from torch/pydub are caught
  and re-raised as one of the two types above.
"""

from __future__ import annotations

import io
import logging

import numpy as np

log = logging.getLogger("voiceattend.voice_service")

# ─────────────────────────────────────────────────────────────────────────────
# Heavy dependency imports — module-level so Render pays the cost once
# ─────────────────────────────────────────────────────────────────────────────
# We raise RuntimeError (not ImportError) so a missing dep surfaces as a
# clear service error rather than an import-time crash that can mask the
# real root cause in Render logs.

try:
    import torch
    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False
    log.error(
        "torch is not installed. "
        "Add 'torch' to requirements.txt. "
        "Voice embedding extraction will fail at runtime."
    )

try:
    from pydub import AudioSegment
    _PYDUB_AVAILABLE = True
except ImportError:
    _PYDUB_AVAILABLE = False
    log.error(
        "pydub is not installed. "
        "Add 'pydub' to requirements.txt and 'ffmpeg' to packages.txt on Render. "
        "Voice embedding extraction will fail at runtime."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Module-level constants — inspectable by callers / tests
# ─────────────────────────────────────────────────────────────────────────────

TARGET_SR: int          = 16_000   # Hz  — ECAPA-TDNN trained at 16 kHz
MIN_DURATION_SEC: float = 2.0      # seconds — reject clips shorter than this
ENERGY_RMS_FLOOR: float = 1e-4     # below this RMS → treat as silent
ENERGY_RMS_CEIL:  float = 1.0      # above this RMS → clipping / corrupt signal


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _check_deps() -> None:
    """Raise RuntimeError if a required native dependency is missing."""
    if not _TORCH_AVAILABLE:
        raise RuntimeError(
            "torch is not installed — cannot extract voice embeddings. "
            "Add 'torch' to requirements.txt."
        )
    if not _PYDUB_AVAILABLE:
        raise RuntimeError(
            "pydub is not installed — cannot decode audio. "
            "Add 'pydub' to requirements.txt and 'ffmpeg' to packages.txt on Render."
        )


def _decode_to_samples(audio_bytes: bytes) -> np.ndarray:
    """
    Decode raw audio bytes (any pydub-supported container) into a
    float32 numpy array normalised to [-1, 1] at TARGET_SR, mono.

    Returns
    -------
    np.ndarray
        Shape (N,), dtype float32, values in [-1.0, 1.0].

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
            "Failed to decode audio. "
            "Accepted formats: WAV, WebM, OGG, MP3, FLAC. "
            f"Detail: {exc}"
        ) from exc

    # Normalise: mono · 16 kHz · 16-bit PCM
    try:
        seg = (
            seg
            .set_channels(1)
            .set_frame_rate(TARGET_SR)
            .set_sample_width(2)    # 16-bit = 2 bytes
        )
    except Exception as exc:
        raise ValueError(f"Audio resampling failed: {exc}") from exc

    samples = np.frombuffer(seg.raw_data, dtype=np.int16).astype(np.float32)
    samples /= 32_768.0             # PCM int16 → float32 [-1, 1]

    return samples


def _validate_samples(samples: np.ndarray) -> None:
    """
    Reject audio that is too short, silent, or heavily clipped/corrupt.

    Raises
    ------
    ValueError with a user-readable message.
    """
    if samples.size == 0:
        raise ValueError("Decoded audio has zero samples.")

    duration_sec: float = len(samples) / TARGET_SR

    if duration_sec < MIN_DURATION_SEC:
        raise ValueError(
            f"Audio too short ({duration_sec:.2f}s). "
            f"Please record at least {MIN_DURATION_SEC:.0f} seconds of clear speech."
        )

    rms: float = float(np.sqrt(np.mean(samples ** 2)))

    if rms < ENERGY_RMS_FLOOR:
        raise ValueError(
            f"Audio appears to be silent (RMS = {rms:.2e}). "
            "Please check your microphone and try again."
        )

    if rms > ENERGY_RMS_CEIL:
        raise ValueError(
            f"Audio is severely clipped or corrupt (RMS = {rms:.3f} > {ENERGY_RMS_CEIL}). "
            "Please re-record in a quieter environment without distortion."
        )

    log.debug(
        "Audio validated: duration=%.2fs  rms=%.5f  samples=%d",
        duration_sec, rms, len(samples),
    )


def _to_unit_vector(vector: np.ndarray) -> np.ndarray:
    """
    Return the L2-normalised (unit) version of `vector`.

    Also validates that the vector:
      - is 1-D
      - contains no NaN or Inf values
      - is not a zero vector

    Raises
    ------
    RuntimeError
        If any of the above checks fail — these indicate an inference
        problem, not a user input problem.
    """
    # ── shape ────────────────────────────────────────────────────────────────
    vector = vector.flatten().astype(np.float32)

    if vector.ndim != 1 or vector.size == 0:
        raise RuntimeError(
            f"Unexpected embedding shape after squeeze: {vector.shape}. "
            "Expected a 1-D vector."
        )

    # ── numerical validity ────────────────────────────────────────────────────
    if not np.isfinite(vector).all():
        n_bad = int(np.sum(~np.isfinite(vector)))
        raise RuntimeError(
            f"Embedding contains {n_bad} NaN/Inf value(s) — "
            "inference produced corrupt output. Check model state."
        )

    # ── zero vector ───────────────────────────────────────────────────────────
    norm = float(np.linalg.norm(vector))
    if norm < 1e-10:
        raise RuntimeError(
            "Embedding is a zero vector — audio may be corrupt, "
            "too noisy, or the model produced degenerate output."
        )

    return vector / norm


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def extract_voice_embedding(audio_bytes: bytes, model) -> list[float]:
    """
    Extract an L2-normalised speaker embedding from raw audio bytes.

    Parameters
    ----------
    audio_bytes : bytes
        Raw audio content (WAV, WebM, OGG, MP3, or FLAC).
    model : SpeechBrain SpeakerRecognition
        ECAPA-TDNN instance from ``app.state.verifier``.
        The caller MUST guard against None and return HTTP 503 before
        invoking this function. Passing None here is a caller bug.

    Returns
    -------
    list[float]
        1-D L2-normalised embedding vector (192-dim for ECAPA-TDNN).
        Cosine similarity between two such vectors:
            similarity = float(np.dot(a, b))

    Raises
    ------
    ValueError
        Bad, too-short, or silent audio  →  caller returns HTTP 422.
    RuntimeError
        Inference failure or degenerate embedding  →  caller returns HTTP 422.
    """
    # ── 0. Dependency guard ──────────────────────────────────────────────────
    _check_deps()

    # ── 0b. Model guard ──────────────────────────────────────────────────────
    # Explicit check with a clear message. This should never trigger if the
    # calling route correctly guards with `if app.state.verifier is None → 503`.
    if model is None:
        raise RuntimeError(
            "model is None. "
            "The calling route must check app.state.verifier before invoking "
            "extract_voice_embedding()."
        )

    # ── 1. Decode + resample to 16 kHz mono float32 ──────────────────────────
    samples = _decode_to_samples(audio_bytes)

    # ── 2. Validate duration + energy ────────────────────────────────────────
    _validate_samples(samples)

    # ── 3. Build input tensor ────────────────────────────────────────────────
    # encode_batch expects shape (batch, time) with float32 in [-1, 1].
    wav_tensor = torch.tensor(samples, dtype=torch.float32).unsqueeze(0)  # (1, N)
    wav_lens   = torch.tensor([1.0])                                       # relative length

    log.debug(
        "Starting ECAPA inference: shape=%s  duration=%.2fs",
        tuple(wav_tensor.shape), len(samples) / TARGET_SR,
    )

    # ── 4. Inference (CPU-only, no_grad) ─────────────────────────────────────
    try:
        with torch.no_grad():
            raw_embedding = model.encode_batch(wav_tensor, wav_lens)
            # encode_batch returns (batch, 1, embedding_dim) e.g. (1, 1, 192)
    except Exception as exc:
        raise RuntimeError(f"ECAPA-TDNN inference failed: {exc}") from exc

    # ── 5. Squeeze → 1-D float32 numpy ───────────────────────────────────────
    emb_np: np.ndarray = raw_embedding.squeeze().cpu().numpy().astype(np.float32)

    log.debug(
        "Raw embedding: shape=%s  norm=%.4f",
        emb_np.shape, float(np.linalg.norm(emb_np)),
    )

    # ── 6. Validate + L2 normalise ───────────────────────────────────────────
    emb_unit = _to_unit_vector(emb_np)

    log.info(
        "Embedding extracted: dim=%d  post-norm=%.6f",
        emb_unit.size, float(np.linalg.norm(emb_unit)),
    )

    # ── 7. Return JSON-serialisable list ─────────────────────────────────────
    return emb_unit.tolist()


# Public alias used by auth.py (voice-login route).
# Both names call exactly the same function — there is one implementation.
extract_embedding_from_bytes = extract_voice_embedding
