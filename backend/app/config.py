"""Central configuration loaded from environment variables / .env file."""

from typing import Any, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    # Groq (Free LLM)
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"

    # Whisper STT (Local)
    whisper_model_size: str = "base"  # tiny | base | small | tiny.en
    whisper_model: str = ""
    whisper_device: str = "cpu"  # cpu | cuda

    # TTS
    tts_provider: str = "edge-tts"
    tts_language: str = "en"

    # Database
    db_url: str = "sqlite+aiosqlite:///./voice_assistant.db"

    # App
    app_name: str = "TS Voice Assistant"
    app_version: str = "1.0.0"
    max_history_messages: int = 20
    cors_origins: Union[list[str], str] = ["*"]
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                try:
                    import json
                    return json.loads(v)
                except Exception:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        if isinstance(v, list):
            return v
        return ["*"]

    @property
    def effective_whisper_model(self) -> str:
        return self.whisper_model or self.whisper_model_size or "base"

    @property
    def sync_db_url(self) -> str:
        """Return synchronous SQLAlchemy URL for LangChain SQLChatMessageHistory."""
        return self.db_url.replace("+aiosqlite", "")


settings = Settings()
