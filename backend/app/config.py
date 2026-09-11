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
    image_upload_max_size_mb: int = 5
    image_expire_hours: int = 24
    image_storage_driver: str = "local"
    image_upload_dir: str = "backend/uploads"
    knowledge_cache_path: str = "data/knowledge_cache.sqlite3"
    wikidata_enabled: bool = True
    conceptnet_enabled: bool = False
    tencent_word2vec_enabled: bool = True
    tencent_word2vec_model_path: str = (
        "data/models/light_Tencent_AILab_ChineseEmbedding.bin"
    )
    tencent_word2vec_topn: int = Field(default=6, ge=1, le=20)
    tencent_word2vec_min_similarity: float = Field(default=0.55, ge=0, le=1)
    wikidata_endpoint: str = "https://www.wikidata.org/w/api.php"
    conceptnet_endpoint: str = "https://api.conceptnet.io"
    knowledge_user_agent: str = "PaintingEasy/0.1 knowledge-expansion (local deployment)"
    knowledge_http_timeout_seconds: float = 2.5
    knowledge_retry_count: int = 1
    knowledge_concurrency_limit: int = 2
    knowledge_circuit_failure_threshold: int = 3
    knowledge_circuit_cooldown_seconds: float = 30
    knowledge_cache_success_ttl_seconds: int = Field(default=2_592_000, ge=1)
    knowledge_cache_empty_ttl_seconds: int = Field(default=86_400, ge=1)
    knowledge_cache_failure_ttl_seconds: int = Field(default=300, ge=1)
    knowledge_cache_stale_ttl_seconds: int = Field(default=7_776_000, ge=1)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
