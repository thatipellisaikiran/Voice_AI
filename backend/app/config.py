"""Central configuration loaded from environment variables / .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    # Groq (Free LLM)
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-70b-versatile"

    # Whisper STT (Local)
    whisper_model_size: str = "base"  # tiny | base | small
    whisper_device: str = "cpu"  # cpu | cuda

    # TTS
    tts_provider: str = "gtts"
    tts_language: str = "en"

    # Database
    db_url: str = "sqlite+aiosqlite:///./voice_assistant.db"

    # App
    app_name: str = "TS Voice Assistant"
    app_version: str = "1.0.0"
    max_history_messages: int = 20
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def sync_db_url(self) -> str:
        """Return synchronous SQLAlchemy URL for LangChain SQLChatMessageHistory."""
        return self.db_url.replace("+aiosqlite", "")


settings = Settings()

