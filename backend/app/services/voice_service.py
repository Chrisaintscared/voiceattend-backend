"""
VoiceAttend AI - Dummy Voice Service
No audio processing. For testing only.
"""
import random


def extract_voice_embedding(audio_bytes: bytes) -> list:
    """Return a random embedding — no real processing."""
    return [random.uniform(-1, 1) for _ in range(128)]


def find_best_match(query_embedding: list, profiles: list):
    """Always return the first profile as a match."""
    if not profiles:
        return None, 0.0
    return profiles[0], 0.99
