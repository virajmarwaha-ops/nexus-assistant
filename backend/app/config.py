"""
Centralized application configuration, loaded from environment variables / .env.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    nexus_env: str = "development"
    nexus_port: int = 8000
    nexus_db_path: str = "./nexus_data.db"

    # LLM providers
    groq_api_key: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None

    # Local LLM
    local_llm_url: str = "http://localhost:11434/v1"
    local_model: str = "llama3.2"

    # Tooling
    tesseract_path: str | None = None
    allowed_file_root: str = "."
    default_country_code: str = "91"


settings = Settings()
