from app.config import Settings
from app.infrastructure.cache import InMemoryTTLCache
from app.models.schemas import KnowledgeExpansionResult
from app.services.rag import KeywordRetriever

from .providers import TencentWord2VecKnowledgeProvider


def build_keyword_retriever(settings: Settings) -> KeywordRetriever:
    cache = InMemoryTTLCache[KnowledgeExpansionResult](
        max_entries=settings.search_cache_max_entries,
        ttl_seconds=settings.search_cache_ttl_seconds,
    )
    provider = TencentWord2VecKnowledgeProvider(
        settings.tencent_word2vec_model_path,
        enabled=settings.tencent_word2vec_enabled,
        topn=settings.tencent_word2vec_topn,
        min_similarity=settings.tencent_word2vec_min_similarity,
        cache=cache,
    )
    return KeywordRetriever(expansion_provider=provider)
