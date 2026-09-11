"""Explicit public-network smoke test; never imported by the unit-test suite."""

from __future__ import annotations

import asyncio
import json
import math
import os
import tempfile
import time
from collections import Counter
from pathlib import Path

import httpx

PROBES = {
    "wikidata": (
        "https://www.wikidata.org/w/api.php",
        {
            "action": "wbsearchentities",
            "search": "painting",
            "language": "en",
            "limit": 1,
            "format": "json",
        },
    ),
    "conceptnet": ("https://api.conceptnet.io/c/en/painting", {"limit": 1}),
}


def percentile_95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)], 1)


def probe_public_services() -> list[dict]:
    summaries = []
    headers = {"User-Agent": "PaintingEasy/0.1 knowledge-expansion (deployment smoke)"}
    with httpx.Client(timeout=6, headers=headers, follow_redirects=True) as client:
        for provider, (endpoint, params) in PROBES.items():
            codes: Counter[int] = Counter()
            latencies = []
            timeouts = 0
            retry_after = 0
            for _ in range(5):
                started = time.perf_counter()
                try:
                    response = client.get(endpoint, params=params)
                    latencies.append((time.perf_counter() - started) * 1000)
                    codes[response.status_code] += 1
                    retry_after += int("retry-after" in response.headers)
                except httpx.TimeoutException:
                    timeouts += 1
            summaries.append(
                {
                    "provider": provider,
                    "status_codes": dict(codes),
                    "p95_ms": percentile_95(latencies),
                    "timeouts": timeouts,
                    "rate_limited": codes[429],
                    "retry_after_headers": retry_after,
                }
            )
    return summaries


async def probe_search_api() -> dict:
    os.environ["WIKIDATA_ENABLED"] = "true"
    os.environ["CONCEPTNET_ENABLED"] = "true"
    os.environ["KNOWLEDGE_CACHE_SUCCESS_TTL_SECONDS"] = "1"
    os.environ["KNOWLEDGE_CACHE_STALE_TTL_SECONDS"] = "60"
    os.environ["KNOWLEDGE_HTTP_TIMEOUT_SECONDS"] = "6"
    cache_path = Path(tempfile.gettempdir()) / "painting_easy_network_smoke.sqlite3"
    try:
        cache_path.unlink(missing_ok=True)
    except PermissionError:
        pass
    os.environ["KNOWLEDGE_CACHE_PATH"] = str(cache_path)

    from app.api import routes
    from app.config import Settings
    from app.knowledge.runtime import build_keyword_retriever
    from app.main import app
    from app.providers import InMemoryUsageQuota, MockLanguageModelProvider
    from app.services import KeywordOptimizeService

    settings = Settings(_env_file=None)
    routes.search_optimizer = KeywordOptimizeService(
        retriever=build_keyword_retriever(settings),
        llm_provider=MockLanguageModelProvider(),
        quota=InMemoryUsageQuota(settings.ai_smart_quota),
    )
    transport = httpx.ASGITransport(app=app)

    async def search(query: str) -> list[str]:
        async with httpx.AsyncClient(transport=transport, base_url="http://smoke") as client:
            response = await client.post(
                "/api/v1/search/assist",
                json={"query": query, "language": "en", "network_expansion": True},
            )
            response.raise_for_status()
            return [item["status"] for item in response.json()["knowledge_sources"]]

    real = await search("painting")
    providers = routes.search_optimizer.retriever.external_orchestrator.providers

    def fixture_success(request: httpx.Request) -> httpx.Response:
        if "wikidata" in request.url.host:
            if request.url.params.get("action") == "wbgetentities":
                payload = {
                    "entities": {
                        "Q1": {
                            "labels": {"en": {"value": "painting"}},
                            "aliases": {"en": [{"value": "art painting"}]},
                        }
                    }
                }
            else:
                payload = {"search": [{"id": "Q1", "label": "painting"}]}
        else:
            payload = {
                "edges": [
                    {
                        "@id": "/a/smoke",
                        "rel": {"label": "RelatedTo"},
                        "start": {"@id": "/c/en/painting_fixture", "language": "en"},
                        "end": {"@id": "/c/en/art", "label": "art", "language": "en"},
                        "weight": 1,
                        "license": "cc:by/4.0",
                    }
                ]
            }
        return httpx.Response(200, request=request, json=payload)

    fixture_transport = httpx.MockTransport(fixture_success)
    providers[0].client = httpx.Client(transport=fixture_transport)
    providers[1].client = httpx.Client(transport=fixture_transport)
    live = await search("painting fixture")
    fresh = await search("painting fixture")

    def unavailable(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    providers[1].client = httpx.Client(transport=httpx.MockTransport(unavailable))
    partial = await search("landscape painting")
    await asyncio.sleep(1.1)
    providers[0].client = httpx.Client(transport=httpx.MockTransport(unavailable))
    stale = await search("painting fixture")
    original = await search("public smoke fallback token")
    try:
        cache_path.unlink(missing_ok=True)
    except PermissionError:
        pass
    return {
        "real_network": real,
        "controlled_fixture_states": {
            "live": live,
            "fresh_cache": fresh,
            "partial_success": partial,
            "stale_cache": stale,
            "original_fallback": original,
        },
    }


if __name__ == "__main__":
    report = {
        "public_connectivity": probe_public_services(),
        "search_api_states": asyncio.run(probe_search_api()),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
