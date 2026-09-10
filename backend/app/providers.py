from hashlib import sha256
from typing import Protocol


class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class LanguageModelProvider(Protocol):
    def generate_keywords(self, prompt: str) -> dict: ...


class MockEmbeddingProvider:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[round(byte / 255, 6) for byte in sha256(text.encode()).digest()[:8]] for text in texts]


class MockLanguageModelProvider:
    def generate_keywords(self, prompt: str) -> dict:
        import re
        original = re.search(r"原始描述：(.+)", prompt)
        query = original.group(1).strip() if original else ""
        derived = []
        if "暖色" in query or "warm" in query.lower():
            derived.append({"keyword": "warm lighting", "category": "color", "source": "mock", "selected": True, "confidence": 0.78, "reason": "根据检索到的色彩规则扩展"})
        return {"preserved_terms": [], "derived_terms": derived, "platform_queries": []}
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
import json

from app.models.schemas import ImageMetadata, SearchSuggestion

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
    def __init__(self, directory: str): self.directory, self.metadata = Path(directory), {}
    def save(self, content, metadata): self.directory.mkdir(parents=True, exist_ok=True); (self.directory / metadata.stored_filename).write_bytes(content); self.metadata[metadata.image_id] = metadata; return metadata
    def get(self, image_id):
        item = self.metadata.get(image_id)
        return item if item and item.status == "active" and item.expires_at > datetime.now(timezone.utc) else None
    def delete(self, image_id):
        item = self.metadata.pop(image_id, None)
        if item: (self.directory / item.stored_filename).unlink(missing_ok=True)
    def cleanup_expired(self, now=None):
        now = now or datetime.now(timezone.utc); keys = [k for k, v in self.metadata.items() if v.expires_at <= now]
        for key in keys: self.delete(key)
        return len(keys)

class ImageAnalyzeProvider(ABC):
    @abstractmethod
    def analyze(self, image: ImageMetadata) -> list[SearchSuggestion]: ...

class MockImageAnalyzeProvider(ImageAnalyzeProvider):
    def analyze(self, image, persona=None, platform=None):
        rules = json.loads((Path(__file__).parent / "data" / "image_keyword_rules.json").read_text(encoding="utf-8"))
        suggestions = [SearchSuggestion(**item, source="mock") for item in rules["objects"]]
        for key in ("personas", "platforms"):
            item = rules[key].get(persona if key == "personas" else platform.lower() if platform else "")
            if item:
                suggestions.append(SearchSuggestion(**item, source="mock"))
        return suggestions

    def analyze_for_platform(self, image, platform: str) -> list[SearchSuggestion]:
        rules = json.loads((Path(__file__).parent / "data" / "image_keyword_rules.json").read_text(encoding="utf-8"))
        suggestions = self.analyze(image, platform=platform)
        item = rules["platforms"].get(platform.lower())
        return suggestions + ([SearchSuggestion(**item, source="mock")] if item else [])
