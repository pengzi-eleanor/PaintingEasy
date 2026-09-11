import json
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from threading import Lock
from typing import Protocol

from pydantic import ValidationError

from app.models.schemas import (
    ImageMetadata,
    SearchSuggestion,
    SmartOptimizationOutput,
)


class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class LanguageModelProvider(Protocol):
    def generate_keywords(self, prompt: str) -> SmartOptimizationOutput: ...


class LanguageModelError(RuntimeError):
    """Sanitized provider error safe for service-level fallback."""


class QuotaExceededError(LanguageModelError):
    pass


class InMemoryUsageQuota:
    def __init__(self, limit: int):
        self._remaining = max(0, limit)
        self._lock = Lock()

    @property
    def remaining(self) -> int:
        with self._lock:
            return self._remaining

    def consume(self) -> int:
        with self._lock:
            if self._remaining <= 0:
                raise QuotaExceededError("smart quota exhausted")
            self._remaining -= 1
            return self._remaining


def parse_structured_model_response(raw_response: str) -> SmartOptimizationOutput:
    """Parse raw provider text inside the provider boundary only."""
    try:
        return SmartOptimizationOutput.model_validate_json(raw_response)
    except ValidationError as exc:
        raise LanguageModelError("invalid structured model response") from exc


class MockEmbeddingProvider:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [
            [round(byte / 255, 6) for byte in sha256(text.encode()).digest()[:8]]
            for text in texts
        ]


class MockLanguageModelProvider:
    def generate_keywords(self, prompt: str) -> SmartOptimizationOutput:
        payload = json.loads(prompt)
        query = payload["original_description"]
        candidates = payload["knowledge_candidates"]
        derived = []
        if "暖色" in query or "warm" in query.casefold():
            derived.append(
                {
                    "keyword": "warm lighting",
                    "category": "color",
                    "derived_from": [query],
                    "reason": "根据原始描述中的暖色意图扩展",
                }
            )
        for item in candidates[: max(0, 8 - len(derived))]:
            derived.append(
                {
                    "keyword": item["term"],
                    "category": item["category"],
                    "derived_from": [item["term"]],
                    "reason": item["reason"],
                }
            )
        plans = [
            {"platform_id": item["id"], "priority": index, "reason": item["reason"]}
            for index, item in enumerate(payload["allowed_platforms"][:5], start=1)
        ]
        raw = json.dumps(
            {
                "core_intent_category": "general",
                "core_terms": [
                    {
                        "keyword": query,
                        "category": "general",
                        "derived_from": [query],
                        "reason": "保留原始描述作为核心意图",
                    }
                ],
                "expanded_terms": derived,
                "uncertainties": [],
                "platform_plans": plans,
            },
            ensure_ascii=False,
        )
        return parse_structured_model_response(raw)


class ImageStorageProvider(ABC):
    @abstractmethod
    def save(self, content: bytes, metadata: ImageMetadata) -> ImageMetadata: ...

    @abstractmethod
    def get(self, image_id: str) -> ImageMetadata | None: ...

    @abstractmethod
    def delete(self, image_id: str) -> None: ...

    @abstractmethod
    def cleanup_expired(self, now: datetime | None = None) -> int: ...


class LocalImageStorageProvider(ImageStorageProvider):
    def __init__(self, directory: str):
        self.directory = Path(directory)
        self.metadata = {}

    def save(self, content, metadata):
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / metadata.stored_filename).write_bytes(content)
        self.metadata[metadata.image_id] = metadata
        return metadata

    def get(self, image_id):
        item = self.metadata.get(image_id)
        if item and item.status == "active" and item.expires_at > datetime.now(UTC):
            return item
        return None

    def delete(self, image_id):
        item = self.metadata.pop(image_id, None)
        if item:
            (self.directory / item.stored_filename).unlink(missing_ok=True)

    def cleanup_expired(self, now=None):
        now = now or datetime.now(UTC)
        keys = [key for key, value in self.metadata.items() if value.expires_at <= now]
        for key in keys:
            self.delete(key)
        return len(keys)


class ImageAnalyzeProvider(ABC):
    @abstractmethod
    def analyze(self, image: ImageMetadata) -> list[SearchSuggestion]: ...


class MockImageAnalyzeProvider(ImageAnalyzeProvider):
    @staticmethod
    def _rules():
        path = Path(__file__).parent / "data" / "image_keyword_rules.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def analyze(self, image, persona=None, platform=None):
        rules = self._rules()
        suggestions = [SearchSuggestion(**item, source="mock") for item in rules["objects"]]
        for key in ("personas", "platforms"):
            lookup = persona if key == "personas" else platform.lower() if platform else ""
            item = rules[key].get(lookup)
            if item:
                suggestions.append(SearchSuggestion(**item, source="mock"))
        return suggestions

    def analyze_for_platform(self, image, platform: str) -> list[SearchSuggestion]:
        rules = self._rules()
        suggestions = self.analyze(image, platform=platform)
        item = rules["platforms"].get(platform.lower())
        return suggestions + ([SearchSuggestion(**item, source="mock")] if item else [])
