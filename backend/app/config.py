from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    secret_key: str = "CHANGE_ME"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    voice_similarity_threshold: float = 0.75

    app_name: str = "VoiceAttend AI"
    debug: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
