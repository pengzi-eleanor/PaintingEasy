from pathlib import Path

import numpy as np

from app.config import Settings
from app.infrastructure.cache import InMemoryTTLCache
from app.knowledge.providers import TencentWord2VecKnowledgeProvider
from app.knowledge.runtime import build_keyword_retriever
from app.models.schemas import KnowledgeExpansionRequest, KnowledgeExpansionResult
from app.services.keyword_optimizer import KeywordOptimizeService
from app.services.rag import ContextBuilder, KeywordRetriever


def write_model(path: Path) -> None:
    words = {
        "咖啡店": [1.0, 0.0],
        "咖啡馆": [0.99, 0.01],
        "甜品店": [0.9, 0.1],
        "夜景": [0.0, 1.0],
    }
    with path.open("wb") as stream:
        stream.write(f"{len(words)} 2\n".encode())
        for word, vector in words.items():
            stream.write(word.encode())
            stream.write(b" ")
            stream.write(np.asarray(vector, dtype="<f4").tobytes())
            stream.write(b"\n")


def test_tencent_provider_returns_stable_terms_and_hits_cache(tmp_path: Path) -> None:
    model = tmp_path / "tencent.bin"
    write_model(model)
    cache = InMemoryTTLCache[KnowledgeExpansionResult](max_entries=2, ttl_seconds=60)
    provider = TencentWord2VecKnowledgeProvider(
        model, topn=2, min_similarity=0.5, cache=cache
    )
    request = KnowledgeExpansionRequest(query="咖啡店")

    first = provider.expand(request)
    second = provider.expand(request)

    assert [item.term for item in first.candidates] == ["咖啡馆", "甜品店"]
    assert first.source_status == "live"
    assert second.source_status == "fresh_cache"


def test_tencent_failure_preserves_retrieval_flow(tmp_path: Path) -> None:
    provider = TencentWord2VecKnowledgeProvider(tmp_path / "missing.bin")
    retriever = KeywordRetriever(expansion_provider=provider)
    result = KeywordOptimizeService(retriever=retriever).optimize("咖啡店")

    assert result.suggestions[0].keyword == "咖啡店"
    assert retriever.provider_degraded is True
    assert result.knowledge_sources[0].status == "original_fallback"


def test_runtime_only_builds_tencent_provider(tmp_path: Path) -> None:
    model = tmp_path / "tencent.bin"
    write_model(model)
    retriever = build_keyword_retriever(
        Settings(
            tencent_word2vec_model_path=str(model),
            search_cache_max_entries=4,
            search_cache_ttl_seconds=60,
        )
    )
    assert retriever.provider_name == "tencent_word2vec"


def test_context_builder_keeps_provider_independent_contract() -> None:
    context = ContextBuilder().build(
        "咖啡店海报",
        "graphic_designer",
        {"keywords": [], "persona_rules": [], "platform_rules": [], "knowledge_sources": []},
        allowed_platforms=[{"id": "freepik", "reason": "适合素材搜索"}],
    )
    assert "original_description" in context
    assert "allowed_platforms" in context
    assert "http" not in context


def test_lightweight_cache_evicts_oldest_entry() -> None:
    cache = InMemoryTTLCache[str](max_entries=2, ttl_seconds=60)
    cache.set("a", "A")
    cache.set("b", "B")
    assert cache.get("a") == "A"
    cache.set("c", "C")
    assert cache.get("b") is None
    assert cache.get("a") == "A"
    assert cache.get("c") == "C"
