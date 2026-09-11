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
    source: Literal["rule", "dictionary", "external", "embedding", "fallback", "mock"] = "mock"
    confidence: float = Field(default=0.5, ge=0, le=1)
    reason: str = ""
    group: Literal["core", "expanded", "platform_specific", "negative"] = "core"
    derived_from: list[str] = Field(default_factory=list)


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
            self.exact_match * 0.35
            + self.semantic_similarity * 0.2
            + self.relation_weight * 0.15
            + self.persona_weight * 0.15
            + self.platform_weight * 0.15,
            6,
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
    group: Literal["core", "expanded", "platform_specific"]
    source: Literal["original", "dictionary", "rule", "external", "embedding", "llm", "fallback"]
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


KnowledgeLanguage = Literal["zh", "en", "mixed", "auto"]
KnowledgeSource = Literal[
    "local_rule", "wikidata", "conceptnet", "tencent_word2vec", "cache", "mock"
]
KnowledgeRelation = Literal[
    "exact",
    "alias",
    "translation",
    "HasType",
    "IsA",
    "UsedFor",
    "AtLocation",
    "RelatedTo",
]


class KnowledgeExpansionContext(BaseModel):
    persona: str | None = None
    platforms: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


class KnowledgeExpansionRequest(BaseModel):
    query: str = Field(max_length=500)
    language: KnowledgeLanguage = "auto"
    context: KnowledgeExpansionContext | None = None

    @field_validator("query")
    @classmethod
    def normalize_expansion_query(cls, value: str) -> str:
        return " ".join(value.split())


class KnowledgeExpansionCandidate(BaseModel):
    term: str = Field(min_length=1, max_length=120)
    language: KnowledgeLanguage
    aliases: list[str] = Field(default_factory=list)
    relation: KnowledgeRelation
    source: KnowledgeSource
    source_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=240)
    confidence: float = Field(ge=0, le=1)
    category: Literal[
        "subject", "scene", "style", "color", "composition", "quality_modifier", "general"
    ] = "general"
    derived_from: list[str] = Field(default_factory=list)
    applicable_platforms: list[str] = Field(default_factory=list)
    license: str | None = None

    @field_validator("term")
    @classmethod
    def normalize_candidate_term(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("term must not be blank")
        return normalized

    @field_validator("aliases")
    @classmethod
    def normalize_aliases(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(" ".join(value.split()) for value in values if value.strip()))


class KnowledgeExpansionResult(BaseModel):
    provider: Literal["local_rule", "wikidata", "conceptnet", "tencent_word2vec", "mock"]
    status: Literal["success", "empty", "failed", "degraded"]
    candidates: list[KnowledgeExpansionCandidate] = Field(default_factory=list)
    version: str
    degraded: bool = False
    warning: str | None = None
    source_status: Literal["fresh_cache", "live", "stale_cache", "original_fallback"] = (
        "original_fallback"
    )

    model_config = {"extra": "forbid"}


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


OptimizationMode = Literal["basic", "smart"]


class SearchAssistRequest(BaseModel):
    query: str = Field(default="", max_length=500)
    language: Literal["auto", "zh", "en"] = "auto"
    persona: str | None = None
    platforms: list[str] | None = None
    optimization_mode: OptimizationMode = "basic"
    network_expansion: bool = True

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
    supports_search_url: bool = True
    interaction_mode: Literal["executable_search", "recommendation_only", "in_site_search"] = (
        "executable_search"
    )
    copyright_status: Literal[
        "inspiration_only",
        "license_per_item",
        "attribution_required",
        "broad_reuse_license",
        "commercial_license",
        "unknown",
    ] = "unknown"
    copyright_notice: str = ""
    recommendation_reason: str = ""
    config_version: str = ""
    score: float = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)


PlatformSearchLink = PlatformQuery


class RetrievalMeta(BaseModel):
    strategy: Literal["rules_only", "external", "hybrid", "fallback"]
    embedding_enabled: bool = False
    embedding_provider: str = "none"
    embedding_model: str = "none"
    knowledge_base_version: str
    candidate_count: int = Field(ge=0)
    degraded: bool = False


class KnowledgeSourceStatus(BaseModel):
    source: Literal["local_rules", "wikidata", "conceptnet", "tencent_word2vec"]
    status: Literal["fresh_cache", "live", "stale_cache", "original_fallback"]
    message: str = ""


class PlatformRecommendation(BaseModel):
    platform: str
    name: str
    rank: int = Field(ge=1)
    reason: str = ""
    homepage_url: str = ""
    supports_search_url: bool = True
    interaction_mode: Literal["executable_search", "recommendation_only", "in_site_search"] = (
        "executable_search"
    )
    requires_login: bool = False
    copyright_status: Literal[
        "inspiration_only",
        "license_per_item",
        "attribution_required",
        "broad_reuse_license",
        "commercial_license",
        "unknown",
    ] = "unknown"
    copyright_notice: str = ""
    config_version: str = ""


class GenerationStatus(BaseModel):
    status: Literal["not_requested", "not_available", "generated", "fallback"]
    ai_used: bool = False
    message: str = ""
    remaining_uses: int | None = Field(default=None, ge=0)


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
    retrieval: RetrievalMeta = RetrievalMeta(
        strategy="fallback", knowledge_base_version="unknown", candidate_count=0
    )
    warnings: list[str] = Field(default_factory=list)
    provider: Literal["mock"] = "mock"
    is_ai_generated: bool = False
    degraded: bool = True
    messages: list[str] = Field(default_factory=list)
    optimization_mode: OptimizationMode = "basic"
    knowledge_sources: list[KnowledgeSourceStatus] = Field(default_factory=list)
    platform_recommendations: list[PlatformRecommendation] = Field(default_factory=list)
    generation_status: GenerationStatus = Field(
        default_factory=lambda: GenerationStatus(
            status="not_requested", ai_used=False, message="基础优化未调用大模型"
        )
    )
    core_intent_category: Literal[
        "subject", "scene", "style", "color", "composition", "general"
    ] = "general"
    uncertainties: list[str] = Field(default_factory=list)


class StructuredKeyword(BaseModel):
    model_config = {"extra": "forbid"}

    keyword: str = Field(min_length=1, max_length=120)
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
    derived_from: list[str] = Field(min_length=1, max_length=4)
    reason: str = Field(min_length=1, max_length=240)

    @field_validator("keyword")
    @classmethod
    def normalize_structured_keyword(cls, value: str) -> str:
        return " ".join(value.split())


class SmartPlatformPlan(BaseModel):
    model_config = {"extra": "forbid"}

    platform_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    priority: int = Field(ge=1, le=5)
    reason: str = Field(min_length=1, max_length=240)


class SmartOptimizationOutput(BaseModel):
    model_config = {"extra": "forbid"}

    core_intent_category: Literal["subject", "scene", "style", "color", "composition", "general"]
    core_terms: list[StructuredKeyword] = Field(default_factory=list, max_length=6)
    expanded_terms: list[StructuredKeyword] = Field(default_factory=list, max_length=8)
    uncertainties: list[str] = Field(default_factory=list, max_length=5)
    platform_plans: list[SmartPlatformPlan] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def validate_unique_and_ranked(self):
        terms = [item.keyword.casefold() for item in (*self.core_terms, *self.expanded_terms)]
        if len(terms) != len(set(terms)):
            raise ValueError("smart keywords must be unique")
        platforms = [item.platform_id for item in self.platform_plans]
        if len(platforms) != len(set(platforms)):
            raise ValueError("smart platforms must be unique")
        priorities = [item.priority for item in self.platform_plans]
        if priorities != sorted(priorities) or len(priorities) != len(set(priorities)):
            raise ValueError("smart platform priorities must be unique and ordered")
        return self


# Historical name retained for callers that validated the earlier mock contract.
MockKeywordOutput = SmartOptimizationOutput


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
