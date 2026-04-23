"""
config.py — load environment variables with sane defaults.
Copy .env.example to .env and fill in real values before running.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://voiceattend_user:voiceattend_pass@localhost:5432/voiceattend"

    # JWT
    secret_key: str = "CHANGE_ME_IN_PRODUCTION_use_openssl_rand_hex_32"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 1 day

    # Voice matching
    voice_similarity_threshold: float = 0.75   # cosine similarity cutoff

    # App
    app_name: str = "VoiceAttend AI"
    debug: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
