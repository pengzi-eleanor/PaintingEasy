import asyncio
from io import BytesIO
from typing import Any

import httpx

from app.main import app
from app.models.schemas import KeywordSuggestion


def request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send())


def test_health() -> None:
    response = request("GET", "/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "creating-easy-backend"}


def test_root_describes_search_endpoint() -> None:
    response = request("GET", "/")
    assert response.status_code == 200
    assert response.json()["message"].startswith("Use POST /api/v1/search/assist")


def test_search_assist_is_cors_accessible() -> None:
    response = request("OPTIONS", "/api/v1/search/assist", headers={
        "Origin": "chrome-extension://painting-easy",
        "Access-Control-Request-Method": "POST",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"


def test_optimize_preserves_original_query() -> None:
    response = request("POST", "/api/text/optimize", json={"query": "  暖色咖啡店海报  "})
    assert response.status_code == 200
    body = response.json()
    assert body["original_query"] == "暖色咖啡店海报"
    assert body["suggestions"][0]["keyword"] == "暖色咖啡店海报"
    assert body["provider"] == "mock"


def test_optimize_rejects_blank_query() -> None:
    assert request("POST", "/api/text/optimize", json={"query": " "}).status_code == 422


def test_search_assist_returns_keywords_and_platform_links() -> None:
    response = request("POST", "/api/v1/search/assist", json={"query": "暖色咖啡店海报"})
    assert response.status_code == 200
    body = response.json()
    assert body["original_query"] == "暖色咖啡店海报"
    assert body["provider"] == "mock"
    assert body["degraded"] is False
    assert len(body["platforms"]) == 6
    assert {item["platform"] for item in body["platforms"]} == {"unsplash", "pexels", "pixabay", "freepik", "vcg", "huaban"}
    assert all("coffee" in item["query"] for item in body["platforms"])


def test_search_assist_rejects_blank_query() -> None:
    response = request("POST", "/api/v1/search/assist", json={"query": " "})
    assert response.status_code == 200
    assert response.json()["suggestions"] == []
    assert response.json()["degraded"] is True


def test_search_assist_chinese_dictionary_keywords() -> None:
    body = request("POST", "/api/v1/search/assist", json={"query": "复古油画风猫"}).json()
    assert {"cat", "oil painting", "vintage"} <= {item["keyword"] for item in body["suggestions"]}


def test_search_assist_english_keywords_are_deduplicated() -> None:
    body = request("POST", "/api/v1/search/assist", json={"query": "vintage vintage cat oil painting"}).json()
    keywords = [item["keyword"] for item in body["suggestions"]]
    assert keywords == ["vintage", "cat", "oil painting"]


def test_search_assist_mixed_keywords() -> None:
    body = request("POST", "/api/v1/search/assist", json={"query": "cyberpunk 城市 night"}).json()
    assert {"cyberpunk", "city", "night"} <= {item["keyword"] for item in body["suggestions"]}


def test_search_assist_provider_failure_degrades() -> None:
    from app.services import KeywordOptimizeService

    class BrokenProvider:
        def suggest(self, query: str) -> list[KeywordSuggestion]:
            raise RuntimeError("offline")

    body = KeywordOptimizeService(BrokenProvider()).optimize("plain query")
    assert body.suggestions[0].source == "fallback"
    assert body.degraded is True


def test_image_analyze_returns_mock_keywords() -> None:
    response = request(
        "POST",
        "/api/image/analyze",
        files={"image": ("sample.png", BytesIO(b"\x89PNG\r\n\x1a\nmock"), "image/png")},
    )
    assert response.status_code == 200
    assert response.json()["filename"] == "sample.png"
    assert response.json()["keywords"][0]["keyword"] == "minimal workspace"


def test_image_analyze_rejects_unsupported_type() -> None:
    response = request(
        "POST",
        "/api/image/analyze",
        files={"image": ("notes.txt", BytesIO(b"not-an-image"), "text/plain")},
    )
    assert response.status_code == 415


def test_image_analyze_rejects_content_type_mismatch() -> None:
    response = request(
        "POST",
        "/api/image/analyze",
        files={"image": ("fake.png", BytesIO(b"not-really-png"), "image/png")},
    )
    assert response.status_code == 422
