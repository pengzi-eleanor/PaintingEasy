from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "creating-easy-backend"


class KeywordSuggestion(BaseModel):
    keyword: str
    category: Literal[
        "subject",
        "scene",
        "style",
        "color",
        "composition",
        "quality",
        "quality_modifier",
        "general",
    ]
    selected: bool = True
    source: Literal["rule", "dictionary", "fallback", "mock"] = "mock"
    confidence: float = Field(default=0.5, ge=0, le=1)
    reason: str = ""
    group: Literal["core", "expanded", "platform_specific", "negative"] = "core"


SearchSuggestion = KeywordSuggestion


class ScoreBreakdown(BaseModel):
    exact_match: float = Field(ge=0, le=1)
    semantic_similarity: float = Field(ge=0, le=1)
    relation_weight: float = Field(ge=0, le=1)
    persona_weight: float = Field(ge=0, le=1)
    platform_weight: float = Field(ge=0, le=1)
    final_score: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_final_score(self):
        expected = round(
            self.exact_match * 0.35 + self.semantic_similarity * 0.2
            + self.relation_weight * 0.15 + self.persona_weight * 0.15
            + self.platform_weight * 0.15, 6
        )
        if abs(self.final_score - expected) > 0.000001:
            raise ValueError(f"final_score must equal deterministic weighted score {expected}")
        return self


class KeywordCandidate(BaseModel):
    id: str = Field(min_length=1)
    concept_id: str | None = None
    keyword: str = Field(min_length=1)
    display_keyword: str = Field(min_length=1)
    language: Literal["zh", "en", "mixed", "auto"]
    category: Literal["subject", "scene", "style", "color", "composition", "quality", "quality_modifier", "general"]
    group: Literal["core", "expanded", "platform_specific"]
    source: Literal["original", "dictionary", "rule", "embedding", "llm", "fallback"]
    selected: bool = True
    removable: bool = True
    scores: ScoreBreakdown
    reason: str = ""
    derived_from: list[str] = Field(default_factory=list)
    applicable_platforms: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_provenance(self):
        if self.source != "original" and (not self.reason.strip() or not self.derived_from):
            raise ValueError("non-original candidates require reason and derived_from")
        return self


class ImageMetadata(BaseModel):
    image_id: str
    original_filename: str
    stored_filename: str
    content_type: str
    size: int
    width: int
    height: int
    url: str
    storage_path: str
    created_at: datetime
    expires_at: datetime
    status: Literal["active", "expired"] = "active"


class ImageUploadResponse(BaseModel):
    image_id: str
    filename: str
    content_type: str
    size: int
    width: int
    height: int
    url: str
    created_at: datetime
    expires_at: datetime
    messages: list[str] = Field(default_factory=list)


class TextOptimizeRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    language: Literal["auto", "zh", "en"] = "auto"

    @field_validator("query")
    @classmethod
    def reject_blank_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query must not be blank")
        return normalized


class TextOptimizeResponse(BaseModel):
    original_query: str
    suggestions: list[KeywordSuggestion]
    provider: Literal["mock"] = "mock"
    is_ai_generated: bool = True


class SearchAssistRequest(BaseModel):
    query: str = Field(default="", max_length=500)
    language: Literal["auto", "zh", "en"] = "auto"
    persona: str | None = None
    platforms: list[str] | None = None

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        return value.strip()


class PlatformQuery(BaseModel):
    platform: str
    name: str
    query: str
    terms: list[str] = Field(default_factory=list)
    core_term_ids: list[str] = Field(default_factory=list)
    expanded_term_ids: list[str] = Field(default_factory=list)
    platform_term_ids: list[str] = Field(default_factory=list)
    url: str
    requires_login: bool = False
    score: float = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)


PlatformSearchLink = PlatformQuery

class RetrievalMeta(BaseModel):
    strategy: Literal["rules_only", "hybrid", "fallback"]
    embedding_enabled: bool = False
    embedding_provider: str = "none"
    embedding_model: str = "none"
    knowledge_base_version: str
    candidate_count: int = Field(ge=0)
    degraded: bool = False


class SearchAssistResponse(BaseModel):
    original_query: str
    query: str
    suggestions: list[KeywordCandidate]
    platforms: list[PlatformQuery]
    core_terms: list[KeywordCandidate] = Field(default_factory=list)
    expanded_terms: list[KeywordCandidate] = Field(default_factory=list)
    platform_terms: list[KeywordCandidate] = Field(default_factory=list)
    default_query: str = ""
    platform_queries: list[PlatformQuery] = Field(default_factory=list)
    retrieval: RetrievalMeta = RetrievalMeta(strategy="fallback", knowledge_base_version="unknown", candidate_count=0)
    warnings: list[str] = Field(default_factory=list)
    provider: Literal["mock"] = "mock"
    is_ai_generated: bool = False
    degraded: bool = True
    messages: list[str] = Field(default_factory=list)


class StructuredKeyword(BaseModel):
    keyword: str
    category: Literal[
        "subject",
        "scene",
        "style",
        "color",
        "composition",
        "quality",
        "quality_modifier",
        "general",
    ]
    source: Literal["retrieved", "mock", "rule", "dictionary", "fallback"]
    selected: bool = True
    confidence: float = Field(ge=0, le=1)
    reason: str


class MockKeywordOutput(BaseModel):
    preserved_terms: list[StructuredKeyword] = Field(default_factory=list)
    derived_terms: list[StructuredKeyword] = Field(default_factory=list)
    platform_queries: list[dict[str, str]] = Field(default_factory=list)


class ImageKeyword(BaseModel):
    keyword: str
    category: Literal["object", "scene", "style", "color", "composition"]
    confidence: float = Field(ge=0, le=1)


class ImageAnalyzeResponse(BaseModel):
    image_id: str = ""
    suggestions: list[KeywordCandidate] = Field(default_factory=list)
    filename: str = ""
    keywords: list[ImageKeyword] = Field(default_factory=list)
    provider: Literal["mock"] = "mock"
    is_ai_generated: bool = True
    degraded: bool = True
    messages: list[str] = Field(default_factory=list)


class AnalyticsEventRequest(BaseModel):
    event_name: str
    session_id: str = Field(min_length=1, max_length=128)
    payload: dict = Field(default_factory=dict)


class AnalyticsEventResponse(BaseModel):
    success: bool
    messages: list[str] = Field(default_factory=list)
