"""
VoiceAttend AI - Dummy Voice Service
No audio processing. No enrollment needed.
"""

def extract_voice_embedding(audio_bytes: bytes) -> list:
    return [0.0] * 128


def find_best_match(query_embedding: list, profiles: list):
    if not profiles:
        return None, 0.0
    return profiles[0], 0.99
