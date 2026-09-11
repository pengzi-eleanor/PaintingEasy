import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import httpx
import numpy as np

from app.config import Settings
from app.knowledge.cache import (
    CACHE_SCHEMA_VERSION,
    RELATION_RULES_VERSION,
    SQLiteKnowledgeCache,
    normalized_query_key,
)
from app.knowledge.orchestrator import (
    CircuitState,
    ExternalKnowledgeOrchestrator,
    ReliabilityPolicy,
)
from app.knowledge.providers import (
    CachedHttpKnowledgeProvider,
    ConceptNetKnowledgeProvider,
    KnowledgeExpansionProvider,
    LocalKnowledgeExpansionProvider,
    TencentWord2VecKnowledgeProvider,
    WikidataKnowledgeProvider,
)
from app.knowledge.runtime import build_keyword_retriever
from app.models.schemas import (
    KnowledgeExpansionCandidate,
    KnowledgeExpansionRequest,
    KnowledgeExpansionResult,
)
from app.services import KeywordOptimizeService, KeywordRetriever


def request(query="咖啡店", language="zh"):
    return KnowledgeExpansionRequest(query=query, language=language)


def write_word2vec_fixture(path):
    entries = [
        ("咖啡店", [1.0, 0.0]),
        ("咖啡馆", [0.99, 0.1]),
        ("咖啡厅", [0.95, 0.15]),
        ("酒吧", [0.0, 1.0]),
    ]
    with path.open("wb") as stream:
        stream.write(f"{len(entries)} 2\n".encode())
        for word, vector in entries:
            stream.write(word.encode("utf-8") + b" ")
            stream.write(np.asarray(vector, dtype="<f4").tobytes())


def test_tencent_word2vec_outputs_stable_chinese_related_terms(tmp_path):
    model_path = tmp_path / "tiny.bin"
    write_word2vec_fixture(model_path)
    provider = TencentWord2VecKnowledgeProvider(model_path, topn=2, min_similarity=0.8)
    result = provider.expand(request("咖啡店"))
    assert result.provider == "tencent_word2vec"
    assert result.status == "success"
    assert [item.term for item in result.candidates] == ["咖啡馆", "咖啡厅"]
    assert all(item.source == "tencent_word2vec" for item in result.candidates)
    assert all(item.derived_from == ["咖啡店"] for item in result.candidates)
    assert provider.expand(request("coffee", "en")).status == "empty"


def test_runtime_enables_official_https_providers_with_identifiable_user_agent(tmp_path):
    settings = Settings(
        _env_file=None,
        wikidata_enabled=True,
        conceptnet_enabled=True,
        knowledge_cache_path=str(tmp_path / "runtime.sqlite3"),
    )
    retriever = build_keyword_retriever(settings, httpx.MockTransport(lambda request: None))
    providers = retriever.external_orchestrator.providers
    assert [provider.enabled for provider in providers] == [True, True]
    assert [provider.endpoint for provider in providers] == [
        "https://www.wikidata.org/w/api.php",
        "https://api.conceptnet.io",
    ]
    assert providers[0].client.headers["User-Agent"].startswith("PaintingEasy/")


def test_local_provider_contract_serialization_and_empty_input():
    provider = LocalKnowledgeExpansionProvider()
    assert isinstance(provider, KnowledgeExpansionProvider)
    result = provider.expand(request())
    assert result.provider == "local_rule" and result.status == "success"
    assert result.candidates[0].reason and result.candidates[0].derived_from
    assert KnowledgeExpansionResult.model_validate_json(result.model_dump_json()) == result
    assert provider.expand(request(" ")).status == "empty"


def test_local_provider_failure_falls_back_and_old_response_is_compatible():
    class Broken:
        name, version, enabled = "local_rule", "broken", True

        def expand(self, value):
            raise RuntimeError("private detail")

    result = KeywordOptimizeService(
        retriever=KeywordRetriever(expansion_provider=Broken())
    ).optimize("咖啡店")
    body = result.model_dump()
    assert "query" in body and "suggestions" in body and "platforms" in body
    assert any(item.keyword == "coffee shop" for item in result.suggestions)


def cached_result(provider="wikidata"):
    candidate = KnowledgeExpansionCandidate(
        term="cafe",
        language="en",
        aliases=["coffee shop"],
        relation="alias",
        source=provider,
        source_id="Q1",
        reason="标签匹配",
        confidence=0.8,
        derived_from=["query-key"],
    )
    return KnowledgeExpansionResult(
        provider=provider, status="success", candidates=[candidate], version=f"{provider}-v1"
    )


def test_sqlite_cache_hit_expiry_version_cleanup_and_privacy(tmp_path):
    path = tmp_path / "knowledge.sqlite3"
    cache = SQLiteKnowledgeCache(path)
    expiry = datetime.now(UTC) + timedelta(minutes=5)
    assert cache.put("wikidata", "zh", "敏感查询", cached_result(), expiry)
    hit = cache.get("wikidata", "zh", "敏感查询", "wikidata-v1")
    assert hit and hit.candidates[0].source == "cache"
    assert cache.get("wikidata", "zh", "敏感查询", "other") is None
    assert "敏感查询" not in path.read_bytes().decode("utf-8", errors="ignore")
    assert len(normalized_query_key("敏感查询")) == 64
    cache.put(
        "wikidata",
        "zh",
        "expired",
        cached_result(),
        datetime.now(UTC) - timedelta(seconds=1),
    )
    assert cache.get("wikidata", "zh", "expired", "wikidata-v1") is None
    assert cache.cleanup() == 1


def test_cache_fresh_and_controlled_stale_windows(tmp_path):
    cache = SQLiteKnowledgeCache(tmp_path / "fresh-stale.sqlite3")
    now = datetime.now(UTC)
    assert cache.put(
        "wikidata",
        "zh",
        "私密描述",
        cached_result(),
        now + timedelta(minutes=1),
        now + timedelta(hours=1),
    )
    assert cache.get_fresh("wikidata", "zh", "私密描述", "wikidata-v1", now)
    assert cache.get_stale("wikidata", "zh", "私密描述", "wikidata-v1", now) is None
    assert (
        cache.get_fresh("wikidata", "zh", "私密描述", "wikidata-v1", now + timedelta(minutes=2))
        is None
    )
    stale = cache.get_stale("wikidata", "zh", "私密描述", "wikidata-v1", now + timedelta(minutes=2))
    assert stale and stale.degraded
    with sqlite3.connect(cache.path) as connection:
        last_accessed_at = connection.execute(
            "SELECT last_accessed_at FROM knowledge_cache"
        ).fetchone()[0]
    assert datetime.fromisoformat(last_accessed_at) == now + timedelta(minutes=2)
    assert (
        cache.get_stale("wikidata", "zh", "私密描述", "wikidata-v1", now + timedelta(hours=1))
        is None
    )


def test_cache_migrates_old_schema_without_losing_fresh_rows(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    now = datetime.now(UTC)
    payload = json.dumps(
        [item.model_dump(mode="json") for item in cached_result().candidates],
        ensure_ascii=False,
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            """CREATE TABLE knowledge_cache (
            provider TEXT NOT NULL, language TEXT NOT NULL, query_key TEXT NOT NULL,
            version TEXT NOT NULL, status TEXT NOT NULL, candidates_json TEXT NOT NULL,
            degraded INTEGER NOT NULL, warning TEXT, created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            PRIMARY KEY(provider, language, query_key, version))"""
        )
        connection.execute(
            "INSERT INTO knowledge_cache VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                "wikidata",
                "zh",
                normalized_query_key("迁移测试"),
                "wikidata-v1",
                "success",
                payload,
                0,
                None,
                now.isoformat(),
                (now + timedelta(minutes=5)).isoformat(),
            ),
        )
    cache = SQLiteKnowledgeCache(path)
    assert cache.get_fresh("wikidata", "zh", "迁移测试", "wikidata-v1")
    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(knowledge_cache)")}
    assert {
        "validated",
        "stale_until",
        "last_accessed_at",
        "schema_version",
        "rules_version",
        "enabled",
    } <= columns


def test_cache_rejects_disabled_incompatible_and_invalid_rows(tmp_path):
    path = tmp_path / "invalid.sqlite3"
    cache = SQLiteKnowledgeCache(path)
    now = datetime.now(UTC)
    assert cache.put(
        "wikidata",
        "zh",
        "校验测试",
        cached_result(),
        now + timedelta(minutes=1),
        now + timedelta(hours=1),
    )
    key = normalized_query_key("校验测试")
    cases = (
        ("validated=0", ()),
        ("enabled=0", ()),
        ("schema_version=?", (CACHE_SCHEMA_VERSION + 1,)),
        ("rules_version=?", (f"{RELATION_RULES_VERSION}-old",)),
        ("candidates_json=?", ("not-json",)),
    )
    for update, values in cases:
        with sqlite3.connect(path) as connection:
            connection.execute(
                "UPDATE knowledge_cache SET validated=1,enabled=1,schema_version=?,"
                "rules_version=?,candidates_json=? WHERE query_key=?",
                (
                    CACHE_SCHEMA_VERSION,
                    RELATION_RULES_VERSION,
                    json.dumps(
                        [item.model_dump(mode="json") for item in cached_result().candidates]
                    ),
                    key,
                ),
            )
            connection.execute(
                f"UPDATE knowledge_cache SET {update} WHERE query_key=?", (*values, key)
            )
        assert cache.get_fresh("wikidata", "zh", "校验测试", "wikidata-v1", now) is None
    invalid_relation = cached_result("conceptnet")
    assert not cache.put(
        "conceptnet",
        "zh",
        "关系测试",
        invalid_relation,
        now + timedelta(minutes=1),
        now + timedelta(hours=1),
    )


def test_cache_concurrent_reads_writes_and_privacy_columns(tmp_path):
    path = tmp_path / "read-write.sqlite3"
    cache = SQLiteKnowledgeCache(path)
    expires = datetime.now(UTC) + timedelta(minutes=5)
    stale_until = expires + timedelta(hours=1)

    def round_trip(index):
        query = f"不可保存的查询 {index}"
        written = cache.put("wikidata", "zh", query, cached_result(), expires, stale_until)
        return written and cache.get_fresh("wikidata", "zh", query, "wikidata-v1") is not None

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert all(pool.map(round_trip, range(40)))
    database_text = path.read_bytes().decode("utf-8", errors="ignore")
    assert "不可保存的查询" not in database_text
    assert "raw_response" not in database_text
    assert "prompt" not in database_text.casefold()


def test_provider_uses_valid_stale_cache_only_after_live_failure(tmp_path):
    cache = SQLiteKnowledgeCache(tmp_path / "provider-stale.sqlite3")
    now = datetime.now(UTC)
    cache.put(
        "wikidata",
        "zh",
        "咖啡店",
        cached_result(),
        now - timedelta(minutes=1),
        now + timedelta(hours=1),
    )
    provider = WikidataKnowledgeProvider(
        enabled=True,
        cache=cache,
        client=httpx.Client(transport=httpx.MockTransport(lambda value: httpx.Response(503))),
    )
    result = provider.expand(request())
    assert result.status == "success"
    assert result.degraded
    assert result.candidates[0].source == "cache"
    assert "旧缓存" in result.warning


def test_provider_applies_distinct_success_empty_and_failure_ttls(tmp_path):
    class FakeProvider(CachedHttpKnowledgeProvider):
        name = "wikidata"
        version = "wikidata-v1"

        def _fetch(self, value):
            if value.query == "失败":
                raise RuntimeError("offline")
            return KnowledgeExpansionResult(
                provider=self.name,
                version=self.version,
                status="success" if value.query == "成功" else "empty",
                candidates=cached_result().candidates if value.query == "成功" else [],
            )

    path = tmp_path / "ttls.sqlite3"
    provider = FakeProvider(
        enabled=True,
        cache=SQLiteKnowledgeCache(path),
        ttl_seconds=600,
        empty_ttl_seconds=120,
        failure_ttl_seconds=30,
        stale_ttl_seconds=3600,
    )
    provider.expand(request("成功"))
    provider.expand(request("空结果"))
    try:
        provider.expand(request("失败"))
    except RuntimeError:
        pass
    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            "SELECT status,created_at,expires_at,stale_until FROM knowledge_cache"
        ).fetchall()
    durations = {
        status: round((_as_datetime(expires) - _as_datetime(created)).total_seconds())
        for status, created, expires, _ in rows
    }
    assert durations == {"success": 600, "empty": 120, "failed": 30}
    success_row = next(row for row in rows if row[0] == "success")
    assert (
        round((_as_datetime(success_row[3]) - _as_datetime(success_row[1])).total_seconds()) == 3600
    )


def _as_datetime(value):
    return datetime.fromisoformat(value)


def test_unavailable_sqlite_does_not_block_live_provider(tmp_path):
    broken_cache = SQLiteKnowledgeCache(tmp_path)
    provider = WikidataKnowledgeProvider(
        enabled=True,
        cache=broken_cache,
        client=httpx.Client(
            transport=httpx.MockTransport(lambda value: httpx.Response(200, json={"search": []}))
        ),
    )
    assert not broken_cache.available
    assert provider.expand(request()).status == "empty"


def test_sqlite_cache_concurrent_writes_and_unavailable_database(tmp_path):
    cache = SQLiteKnowledgeCache(tmp_path / "concurrent.sqlite3")
    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(
            pool.map(
                lambda index: cache.put(
                    "wikidata",
                    "zh",
                    f"q{index}",
                    cached_result(),
                    datetime.now(UTC) + timedelta(minutes=1),
                ),
                range(20),
            )
        )
    assert all(outcomes)
    broken = SQLiteKnowledgeCache(tmp_path)
    assert not broken.available and broken.get("wikidata", "zh", "q", "v") is None
    corrupt_path = tmp_path / "corrupt.sqlite3"
    corrupt_path.write_bytes(b"not a sqlite database")
    corrupt = SQLiteKnowledgeCache(corrupt_path)
    assert not corrupt.available and corrupt.cleanup() == 0


def test_wikidata_labels_aliases_deduplicate_and_cache(tmp_path):
    calls = 0

    def handler(http_request):
        nonlocal calls
        calls += 1
        if http_request.url.params.get("action") == "wbgetentities":
            return httpx.Response(
                200,
                json={
                    "entities": {
                        "Q1": {
                            "labels": {
                                "zh": {"value": "咖啡馆"},
                                "en": {"value": "cafe"},
                            },
                            "aliases": {
                                "zh": [{"value": "咖啡店"}],
                                "en": [{"value": "coffee shop"}],
                            },
                        }
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "search": [
                    {"id": "Q1", "label": "咖啡馆", "aliases": ["咖啡店", "咖啡店"]},
                    {"id": "Q2", "label": "咖啡馆", "aliases": []},
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = WikidataKnowledgeProvider(
        enabled=True, client=client, cache=SQLiteKnowledgeCache(tmp_path / "cache.sqlite3")
    )
    first, second = provider.expand(request()), provider.expand(request())
    assert calls == 2
    assert first.candidates[0].term == "cafe"
    assert first.candidates[0].aliases == ["咖啡店", "咖啡馆", "coffee shop"]
    assert second.candidates[0].source == "cache"


def test_wikidata_timeout_non_200_and_empty_are_safely_orchestrated():
    for outcome in (httpx.ReadTimeout("timeout"), httpx.Response(503)):

        def handler(http_request, value=outcome):
            if isinstance(value, Exception):
                raise value
            return value

        provider = WikidataKnowledgeProvider(
            enabled=True, client=httpx.Client(transport=httpx.MockTransport(handler))
        )
        results, warnings = ExternalKnowledgeOrchestrator(
            [provider], ReliabilityPolicy(retries=0)
        ).expand(request())
        assert [item.source_status for item in results] == ["original_fallback"]
        assert warnings
    empty = WikidataKnowledgeProvider(
        enabled=True,
        client=httpx.Client(
            transport=httpx.MockTransport(lambda value: httpx.Response(200, json={"search": []}))
        ),
    )
    assert empty.expand(request()).status == "empty"


def test_provider_failure_status_is_cached_without_raw_query(tmp_path):
    cache_path = tmp_path / "failed.sqlite3"
    cache = SQLiteKnowledgeCache(cache_path)
    provider = WikidataKnowledgeProvider(
        enabled=True,
        client=httpx.Client(transport=httpx.MockTransport(lambda value: httpx.Response(503))),
        cache=cache,
    )
    try:
        provider.expand(request("私密描述"))
    except httpx.HTTPStatusError:
        pass
    cached = cache.get("wikidata", "zh", "私密描述", "wikidata-v1")
    assert cached and cached.status == "failed"
    assert "私密描述" not in cache_path.read_bytes().decode("utf-8", errors="ignore")


def test_conceptnet_whitelist_limit_filter_and_stable_sort():
    edges = [
        {
            "@id": "3",
            "rel": {"label": "Causes"},
            "start": {"@id": "/c/en/cafe"},
            "end": {"label": "ignored", "language": "en"},
            "weight": 9,
        },
        {
            "@id": "2",
            "rel": {"label": "RelatedTo"},
            "start": {"@id": "/c/en/cafe"},
            "end": {"label": "drink", "language": "en"},
            "weight": 2,
        },
        {
            "@id": "1",
            "rel": {"label": "AtLocation"},
            "start": {"@id": "/c/en/cafe"},
            "end": {"label": "city", "language": "en"},
            "weight": 1,
        },
    ]
    provider = ConceptNetKnowledgeProvider(
        enabled=True,
        max_candidates=1,
        client=httpx.Client(
            transport=httpx.MockTransport(lambda value: httpx.Response(200, json={"edges": edges}))
        ),
    )
    result = provider.expand(request("cafe", "en"))
    assert [item.term for item in result.candidates] == ["city"]
    assert result.candidates[0].relation == "AtLocation"
    assert result.candidates[0].derived_from


def test_conceptnet_accepts_actual_isa_relation_shape():
    edge = {
        "@id": "isa-1",
        "rel": {"label": "IsA"},
        "start": {"@id": "/c/en/cafe"},
        "end": {"label": "place", "language": "en"},
        "weight": 1,
    }
    provider = ConceptNetKnowledgeProvider(
        enabled=True,
        client=httpx.Client(
            transport=httpx.MockTransport(lambda value: httpx.Response(200, json={"edges": [edge]}))
        ),
    )
    result = provider.expand(request("cafe", "en"))
    assert [(item.term, item.relation) for item in result.candidates] == [("place", "IsA")]


def test_partial_success_circuit_open_and_half_open_recovery():
    class Provider:
        enabled, version = True, "v1"

        def __init__(self, name, failures):
            self.name, self.failures = name, failures

        def expand(self, value):
            if self.failures:
                self.failures -= 1
                raise RuntimeError("offline")
            return KnowledgeExpansionResult(provider=self.name, status="success", version="v1")

    now = [0.0]
    good, bad = Provider("wikidata", 0), Provider("conceptnet", 2)
    orchestrator = ExternalKnowledgeOrchestrator(
        [good, bad],
        ReliabilityPolicy(retries=0, failure_threshold=1, cooldown_seconds=10),
        clock=lambda: now[0],
    )
    results, warnings = orchestrator.expand(request())
    assert [item.provider for item in results] == ["wikidata", "conceptnet"] and warnings
    assert [item.source_status for item in results] == [
        "original_fallback",
        "original_fallback",
    ]
    assert orchestrator.states["conceptnet"].state == CircuitState.OPEN
    orchestrator.expand(request())
    now[0] = 11
    orchestrator.expand(request())
    now[0] = 22
    results, _ = orchestrator.expand(request())
    assert any(item.provider == "conceptnet" for item in results)
    assert orchestrator.states["conceptnet"].state == CircuitState.CLOSED


def _external_providers(handler, cache=None):
    return [
        WikidataKnowledgeProvider(
            enabled=True,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            cache=cache,
        ),
        ConceptNetKnowledgeProvider(
            enabled=True,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            cache=cache,
        ),
    ]


def _dual_success_handler(delay=0):
    def handler(http_request):
        if delay:
            time.sleep(delay)
        if "wikidata" in http_request.url.host:
            return httpx.Response(200, json={"search": [{"label": "cafe"}]})
        return httpx.Response(
            200,
            json={
                "edges": [
                    {
                        "@id": "conceptnet:drink",
                        "rel": {"label": "RelatedTo"},
                        "start": {"@id": http_request.url.path},
                        "end": {"label": "drink", "language": "en"},
                        "weight": 1,
                    }
                ]
            },
        )

    return handler


def _provider_cache_result(provider, version, term):
    relation = "alias" if provider == "wikidata" else "IsA"
    return KnowledgeExpansionResult(
        provider=provider,
        status="success",
        version=version,
        candidates=[
            KnowledgeExpansionCandidate(
                term=term,
                language="en",
                relation=relation,
                source=provider,
                source_id=f"{provider}:{term}",
                reason="脱敏缓存候选",
                confidence=0.7,
                derived_from=["query-key"],
            )
        ],
    )


def test_two_live_providers_run_concurrently_and_keep_stable_order():
    providers = _external_providers(_dual_success_handler(delay=0.15))
    started = time.monotonic()
    results, warnings = ExternalKnowledgeOrchestrator(
        providers, ReliabilityPolicy(retries=0)
    ).expand(request("cafe", "en"))
    elapsed = time.monotonic() - started
    assert elapsed < 0.27
    assert warnings == []
    assert [(item.provider, item.source_status) for item in results] == [
        ("wikidata", "live"),
        ("conceptnet", "live"),
    ]
    assert [item.candidates[0].term for item in results] == ["cafe", "drink"]


def test_fresh_cache_is_independent_and_only_miss_calls_live(tmp_path):
    cache = SQLiteKnowledgeCache(tmp_path / "independent.sqlite3")
    now = datetime.now(UTC)
    cache.put(
        "wikidata",
        "zh",
        "咖啡店",
        _provider_cache_result("wikidata", "wikidata-v1", "cached cafe"),
        now + timedelta(minutes=5),
        now + timedelta(hours=1),
    )
    calls = {"wikidata": 0, "conceptnet": 0}

    def handler(http_request):
        provider = "wikidata" if "wikidata" in http_request.url.host else "conceptnet"
        calls[provider] += 1
        return _dual_success_handler()(http_request)

    results, _ = ExternalKnowledgeOrchestrator(
        _external_providers(handler, cache), ReliabilityPolicy(retries=0)
    ).expand(request())
    assert calls == {"wikidata": 0, "conceptnet": 1}
    assert [item.source_status for item in results] == ["fresh_cache", "live"]


def test_partial_success_and_both_failed_stale_fallbacks(tmp_path):
    def partial_handler(http_request):
        if "wikidata" in http_request.url.host:
            return _dual_success_handler()(http_request)
        return httpx.Response(503)

    partial, warnings = ExternalKnowledgeOrchestrator(
        _external_providers(partial_handler), ReliabilityPolicy(retries=0)
    ).expand(request())
    assert [item.source_status for item in partial] == ["live", "original_fallback"]
    assert [item.candidates[0].term for item in partial if item.candidates] == ["cafe"]
    assert warnings and "503" not in " ".join(warnings)

    cache = SQLiteKnowledgeCache(tmp_path / "both-stale.sqlite3")
    now = datetime.now(UTC)
    for provider, version, term in (
        ("wikidata", "wikidata-v1", "old cafe"),
        ("conceptnet", "conceptnet-5.7", "old place"),
    ):
        cache.put(
            provider,
            "zh",
            "咖啡店",
            _provider_cache_result(provider, version, term),
            now - timedelta(minutes=1),
            now + timedelta(hours=1),
        )

    def failed(value):
        return httpx.Response(503)

    stale_results, stale_warnings = ExternalKnowledgeOrchestrator(
        _external_providers(failed, cache), ReliabilityPolicy(retries=0)
    ).expand(request())
    assert [item.source_status for item in stale_results] == [
        "stale_cache",
        "stale_cache",
    ]
    assert [item.candidates[0].term for item in stale_results] == [
        "old cafe",
        "old place",
    ]
    assert stale_warnings == []


def test_both_failed_without_stale_returns_original_fallback():
    results, warnings = ExternalKnowledgeOrchestrator(
        _external_providers(lambda value: httpx.Response(503)),
        ReliabilityPolicy(retries=0),
    ).expand(request())
    assert [item.source_status for item in results] == [
        "original_fallback",
        "original_fallback",
    ]
    assert all(not item.candidates for item in results)
    assert len(warnings) == 2


def test_request_storm_coalesces_each_provider_live_call(tmp_path):
    calls = {"wikidata": 0, "conceptnet": 0}

    def handler(http_request):
        provider = "wikidata" if "wikidata" in http_request.url.host else "conceptnet"
        calls[provider] += 1
        return _dual_success_handler(delay=0.08)(http_request)

    orchestrator = ExternalKnowledgeOrchestrator(
        _external_providers(handler, SQLiteKnowledgeCache(tmp_path / "storm.sqlite3")),
        ReliabilityPolicy(retries=0),
    )
    with ThreadPoolExecutor(max_workers=12) as pool:
        batches = list(
            pool.map(
                lambda value: orchestrator.expand(request("cafe", "en")),
                range(20),
            )
        )
    assert calls == {"wikidata": 1, "conceptnet": 1}
    assert all(
        [item.candidates[0].term for item in results] == ["cafe", "drink"] for results, _ in batches
    )
