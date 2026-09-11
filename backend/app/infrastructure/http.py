from __future__ import annotations

from time import sleep
from typing import Any, Protocol

import httpx


class ExternalApiError(RuntimeError):
    """Sanitized error raised at the external API boundary."""


class ExternalApiClient(Protocol):
    def request_json(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> Any: ...


class HttpxExternalApiClient:
    """Reusable JSON client for future translation, LLM and vision providers."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 10,
        retries: int = 1,
        client: httpx.Client | None = None,
    ):
        self.timeout_seconds = timeout_seconds
        self.retries = max(0, retries)
        self.client = client or httpx.Client()

    def request_json(self, method: str, url: str, **kwargs: Any) -> Any:
        for attempt in range(self.retries + 1):
            try:
                response = self.client.request(
                    method,
                    url,
                    timeout=self.timeout_seconds,
                    **kwargs,
                )
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                if attempt == self.retries:
                    raise ExternalApiError("external API request failed") from exc
                sleep(min(0.25 * (attempt + 1), 1.0))
        raise ExternalApiError("external API request failed")
