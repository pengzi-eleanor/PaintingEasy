import httpx

from app.config import Settings
from app.services.rag import KeywordRetriever

from .cache import SQLiteKnowledgeCache
from .orchestrator import ExternalKnowledgeOrchestrator, ReliabilityPolicy
from .providers import (
    ConceptNetKnowledgeProvider,
    TencentWord2VecKnowledgeProvider,
    WikidataKnowledgeProvider,
)


def build_keyword_retriever(
    settings: Settings, transport: httpx.BaseTransport | None = None
) -> KeywordRetriever:
    local_provider = (
        TencentWord2VecKnowledgeProvider(
            settings.tencent_word2vec_model_path,
            enabled=True,
            topn=settings.tencent_word2vec_topn,
            min_similarity=settings.tencent_word2vec_min_similarity,
        )
        if settings.tencent_word2vec_enabled
        else None
    )
    if not settings.wikidata_enabled and not settings.conceptnet_enabled:
        return KeywordRetriever(expansion_provider=local_provider, use_local_knowledge=False)
    cache = SQLiteKnowledgeCache(settings.knowledge_cache_path)
    client = httpx.Client(
        timeout=settings.knowledge_http_timeout_seconds,
        transport=transport,
        headers={"User-Agent": settings.knowledge_user_agent},
    )
    providers = []
    if settings.wikidata_enabled:
        providers.append(
            WikidataKnowledgeProvider(
                enabled=settings.wikidata_enabled,
                client=client,
                cache=cache,
                ttl_seconds=settings.knowledge_cache_success_ttl_seconds,
                empty_ttl_seconds=settings.knowledge_cache_empty_ttl_seconds,
                failure_ttl_seconds=settings.knowledge_cache_failure_ttl_seconds,
                stale_ttl_seconds=settings.knowledge_cache_stale_ttl_seconds,
                endpoint=settings.wikidata_endpoint,
            )
        )
    if settings.conceptnet_enabled:
        providers.append(
            ConceptNetKnowledgeProvider(
                enabled=settings.conceptnet_enabled,
                client=client,
                cache=cache,
                ttl_seconds=settings.knowledge_cache_success_ttl_seconds,
                empty_ttl_seconds=settings.knowledge_cache_empty_ttl_seconds,
                failure_ttl_seconds=settings.knowledge_cache_failure_ttl_seconds,
                stale_ttl_seconds=settings.knowledge_cache_stale_ttl_seconds,
                endpoint=settings.conceptnet_endpoint,
            )
        )
    policy = ReliabilityPolicy(
        retries=settings.knowledge_retry_count,
        concurrency=settings.knowledge_concurrency_limit,
        failure_threshold=settings.knowledge_circuit_failure_threshold,
        cooldown_seconds=settings.knowledge_circuit_cooldown_seconds,
    )
    return KeywordRetriever(
        expansion_provider=local_provider,
        external_orchestrator=ExternalKnowledgeOrchestrator(providers, policy),
        use_local_knowledge=False,
    )
