from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CreatingEasy API"
    app_env: str = "development"
    ai_provider_api_key: str | None = None
    ai_provider: str = "mock"
    ai_smart_quota: int = Field(default=20, ge=0)
    analytics_enabled: bool = True
    analytics_provider: str = "jsonl"
    analytics_log_path: str = "backend/logs/events.jsonl"
    analytics_record_raw_query: bool = False
    image_upload_max_size_mb: int = Field(default=10, ge=1, le=50)
    image_expire_hours: int = 24
    image_cleanup_interval_minutes: int = Field(default=60, ge=1, le=1440)
    image_storage_driver: str = "local"
    image_upload_dir: str = "backend/uploads"
    tencent_word2vec_enabled: bool = True
    tencent_word2vec_model_path: str = (
        "data/models/light_Tencent_AILab_ChineseEmbedding.bin"
    )
    tencent_word2vec_topn: int = Field(default=6, ge=1, le=20)
    tencent_word2vec_min_similarity: float = Field(default=0.55, ge=0, le=1)
    search_cache_max_entries: int = Field(default=256, ge=0, le=4096)
    search_cache_ttl_seconds: float = Field(default=900, ge=0, le=86_400)
    external_api_timeout_seconds: float = Field(default=10, gt=0, le=120)
    external_api_retry_count: int = Field(default=1, ge=0, le=5)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
