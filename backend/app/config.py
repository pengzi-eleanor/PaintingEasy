from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CreatingEasy API"
    app_env: str = "development"
    ai_provider_api_key: str | None = None
    analytics_enabled: bool = True
    analytics_provider: str = "jsonl"
    analytics_log_path: str = "backend/logs/events.jsonl"
    analytics_record_raw_query: bool = False
    image_upload_max_size_mb: int = 5
    image_expire_hours: int = 24
    image_storage_driver: str = "local"
    image_upload_dir: str = "backend/uploads"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
