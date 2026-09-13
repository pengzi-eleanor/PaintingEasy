import json
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock, RLock
from typing import Protocol

from pydantic import ValidationError

from app.models.schemas import (
    ImageMetadata,
    SearchSuggestion,
    SmartOptimizationOutput,
)


class LanguageModelProvider(Protocol):
    def generate_keywords(self, prompt: str) -> SmartOptimizationOutput: ...


class TranslationProvider(Protocol):
    def translate(
        self, text: str, *, source_language: str = "auto", target_language: str = "en"
    ) -> str: ...


class LanguageModelError(RuntimeError):
    """Sanitized provider error safe for service-level fallback."""


class QuotaExceededError(LanguageModelError):
    pass


class TranslationProviderError(RuntimeError):
    """Sanitized provider error safe for translation fallback."""


class UnavailableTranslationProvider:
    def translate(
        self, text: str, *, source_language: str = "auto", target_language: str = "en"
    ) -> str:
        raise TranslationProviderError("translation provider is not configured")


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
    def __init__(self, directory: str, *, expire_hours: int = 24):
        self.directory = Path(directory)
        self.metadata = {}
        self.expire_after = timedelta(hours=expire_hours)
        self._lock = RLock()

    def save(self, content, metadata):
        with self._lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            (self.directory / metadata.stored_filename).write_bytes(content)
            self.metadata[metadata.image_id] = metadata
        return metadata

    def get(self, image_id):
        with self._lock:
            item = self.metadata.get(image_id)
        if item and item.status == "active" and item.expires_at > datetime.now(UTC):
            return item
        return None

    def delete(self, image_id):
        with self._lock:
            item = self.metadata.pop(image_id, None)
            if item:
                (self.directory / item.stored_filename).unlink(missing_ok=True)

    def cleanup_expired(self, now=None):
        now = now or datetime.now(UTC)
        with self._lock:
            keys = [key for key, value in self.metadata.items() if value.expires_at <= now]
            for key in keys:
                self.delete(key)
            removed = len(keys)
            active_files = {item.stored_filename for item in self.metadata.values()}
        if not self.directory.exists():
            return removed
        cutoff = now - self.expire_after
        for path in self.directory.iterdir():
            if (
                not path.is_file()
                or not path.name.startswith("img_")
                or path.suffix.casefold() not in {".jpg", ".png", ".webp"}
                or path.name in active_files
            ):
                continue
            modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            if modified_at <= cutoff:
                path.unlink(missing_ok=True)
                removed += 1
        return removed


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
