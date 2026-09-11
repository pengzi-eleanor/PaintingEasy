import httpx
import pytest

from app.infrastructure.http import ExternalApiError, HttpxExternalApiClient
from app.providers import (
    ImageAnalyzeProvider,
    LanguageModelProvider,
    TranslationProvider,
    TranslationProviderError,
    UnavailableTranslationProvider,
)


def test_external_api_client_supports_injected_transport_and_json() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True}))
    client = HttpxExternalApiClient(
        timeout_seconds=1,
        retries=0,
        client=httpx.Client(transport=transport),
    )
    assert client.request_json("GET", "https://provider.test/status") == {"ok": True}


def test_external_api_client_maps_provider_errors() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(503))
    client = HttpxExternalApiClient(retries=0, client=httpx.Client(transport=transport))
    with pytest.raises(ExternalApiError, match="external API request failed"):
        client.request_json("GET", "https://provider.test/status")


def test_future_provider_contracts_remain_available() -> None:
    assert LanguageModelProvider is not None
    assert TranslationProvider is not None
    assert ImageAnalyzeProvider is not None
    with pytest.raises(TranslationProviderError):
        UnavailableTranslationProvider().translate("咖啡店")
