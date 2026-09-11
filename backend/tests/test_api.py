import asyncio
from io import BytesIO
from typing import Any

import httpx

from app.main import app
from app.models.schemas import KeywordSuggestion, SearchAssistRequest, SearchAssistResponse
from app.services.platforms import PLATFORMS


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
    assert body["degraded"] is True
    assert len(body["platforms"]) == len([item for item in PLATFORMS if item.enabled])
    assert {item["platform"] for item in body["platforms"]} == {
        item.id for item in PLATFORMS if item.enabled
    }
    assert all(item["query"] for item in body["platforms"])
    assert all(item["url"] for item in body["platforms"])
    assert body["optimization_mode"] == "basic"
    assert body["generation_status"]["ai_used"] is False
    assert {item["source"] for item in body["knowledge_sources"]} == {
        "wikidata",
    }
    assert {item["status"] for item in body["knowledge_sources"]} == {
        "original_fallback"
    }
    assert body["retrieval"]["strategy"] == "fallback"
    assert len(body["platform_recommendations"]) <= 5


def test_search_assist_keeps_all_persona_platforms() -> None:
    body = request(
        "POST",
        "/api/v1/search/assist",
        json={"query": "品牌海报", "persona": "graphic_designer"},
    ).json()
    assert [item["name"] for item in body["platforms"]] == [
        "花瓣网", "小红书", "Pinterest", "Pixso", "创客贴", "Behance", "Freepik"
    ]
    xiaohongshu = next(item for item in body["platforms"] if item["name"] == "小红书")
    assert xiaohongshu["supports_search_url"] is False
    assert xiaohongshu["url"] == "https://www.xiaohongshu.com/"


def test_search_request_without_mode_keeps_basic_compatibility() -> None:
    request_model = SearchAssistRequest.model_validate({"query": "猫"})
    assert request_model.optimization_mode == "basic"
    assert request_model.network_expansion is True
    serialized = SearchAssistResponse.model_validate(
        request("POST", "/api/v1/search/assist", json={"query": "猫"}).json()
    ).model_dump()
    assert serialized["query"]
    assert serialized["suggestions"]
    assert serialized["platforms"]


def test_user_can_disable_network_expansion_per_request() -> None:
    body = request(
        "POST",
        "/api/v1/search/assist",
        json={"query": "非敏感测试词", "network_expansion": False},
    ).json()
    assert {item["status"] for item in body["knowledge_sources"]} == {
        "original_fallback"
    }
    assert all(
        "关闭" in item["message"] or "未启用" in item["message"]
        for item in body["knowledge_sources"]
    )


def test_smart_mode_uses_structured_offline_mock() -> None:
    body = request(
        "POST",
        "/api/v1/search/assist",
        json={
            "query": "咖啡店海报",
            "persona": "graphic_designer",
            "optimization_mode": "smart",
        },
    ).json()
    assert body["optimization_mode"] == "smart"
    assert body["is_ai_generated"] is True
    assert body["generation_status"]["status"] == "generated"
    assert body["generation_status"]["ai_used"] is True
    assert isinstance(body["generation_status"]["remaining_uses"], int)
    assert body["suggestions"][0]["keyword"] == "咖啡店海报"


def test_search_assist_rejects_blank_query() -> None:
    response = request("POST", "/api/v1/search/assist", json={"query": " "})
    assert response.status_code == 200
    assert response.json()["suggestions"] == []
    assert response.json()["degraded"] is True


def test_search_assist_chinese_keeps_original_without_manual_dictionary() -> None:
    body = request("POST", "/api/v1/search/assist", json={"query": "复古油画风猫"}).json()
    assert [item["keyword"] for item in body["suggestions"]] == ["复古油画风猫"]
    assert body["suggestions"][0]["source"] == "original"


def test_search_assist_english_keeps_normalized_original() -> None:
    body = request(
        "POST",
        "/api/v1/search/assist",
        json={"query": "vintage vintage cat oil painting"},
    ).json()
    keywords = [item["keyword"] for item in body["suggestions"]]
    assert keywords == ["vintage vintage cat oil painting"]


def test_search_assist_mixed_input_keeps_original_intent() -> None:
    body = request("POST", "/api/v1/search/assist", json={"query": "cyberpunk 城市 night"}).json()
    assert [item["keyword"] for item in body["suggestions"]] == ["cyberpunk 城市 night"]


def test_search_assist_provider_failure_degrades() -> None:
    from app.services import KeywordOptimizeService

    class BrokenProvider:
        def suggest(self, query: str) -> list[KeywordSuggestion]:
            raise RuntimeError("offline")

    body = KeywordOptimizeService(BrokenProvider()).optimize("plain query")
    assert body.suggestions[0].source == "original"
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
