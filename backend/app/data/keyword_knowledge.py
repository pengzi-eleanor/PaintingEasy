from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

KeywordCategory = Literal[
    "subject", "scene", "color", "style", "composition", "quality_modifier", "general"
]


class LocalizedTerms(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    zh: list[str] = Field(default_factory=list)
    en: list[str] = Field(default_factory=list)

    @field_validator("zh", "en")
    @classmethod
    def normalize_terms(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class CanonicalTerm(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    zh: str = Field(min_length=1)
    en: str = Field(min_length=1)

    @field_validator("zh", "en")
    @classmethod
    def strip_term(cls, value: str) -> str:
        return value.strip()


class ConceptRelation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    concept_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    relation: Literal["broader", "narrower", "associated", "modifier"]
    weight: float = Field(gt=0, le=1)


class KeywordConcept(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    canonical: CanonicalTerm
    aliases: LocalizedTerms = Field(default_factory=LocalizedTerms)
    category: KeywordCategory
    search_terms: LocalizedTerms
    related_concepts: list[ConceptRelation] = Field(default_factory=list)
    applicable_personas: list[str] = Field(default_factory=list)
    applicable_platforms: list[str] = Field(default_factory=list)
    embedding_text: str = Field(min_length=1, max_length=500)
    enabled: bool = True
    version: int = Field(ge=1)

    @field_validator("embedding_text")
    @classmethod
    def validate_embedding_text(cls, value: str) -> str:
        normalized = re.sub(r"\s+", " ", value).strip()
        if not normalized:
            raise ValueError("embedding_text must not be blank")
        return normalized

    def match_terms(self) -> tuple[str, ...]:
        values = [
            self.canonical.zh,
            self.canonical.en,
            *self.aliases.zh,
            *self.aliases.en,
            *self.search_terms.zh,
            *self.search_terms.en,
        ]
        return tuple(dict.fromkeys(values))


class KeywordKnowledgeBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    concepts: tuple[KeywordConcept, ...]

    @model_validator(mode="after")
    def validate_concepts(self) -> KeywordKnowledgeBase:
        ids = [concept.id for concept in self.concepts]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate concept id")
        semantic_keys: set[tuple[str, str]] = set()
        for concept in self.concepts:
            key = (concept.canonical.zh.casefold(), concept.canonical.en.casefold())
            if key in semantic_keys:
                raise ValueError("duplicate canonical concept")
            semantic_keys.add(key)
        known_ids = set(ids)
        for concept in self.concepts:
            for relation in concept.related_concepts:
                if relation.concept_id == concept.id:
                    raise ValueError(f"self relation on {concept.id}")
                if relation.concept_id not in known_ids:
                    raise ValueError(
                        f"relation from {concept.id} targets missing concept {relation.concept_id}"
                    )
        return self

    @property
    def by_id(self) -> dict[str, KeywordConcept]:
        return {concept.id: concept for concept in self.concepts}


def build_knowledge_base(concepts: Iterable[KeywordConcept | dict]) -> KeywordKnowledgeBase:
    """Validate records and collapse exact duplicates before checking stable IDs."""
    unique: list[KeywordConcept] = []
    fingerprints: set[str] = set()
    for raw in concepts:
        concept = raw if isinstance(raw, KeywordConcept) else KeywordConcept.model_validate(raw)
        fingerprint = concept.model_dump_json()
        if fingerprint not in fingerprints:
            fingerprints.add(fingerprint)
            unique.append(concept)
    return KeywordKnowledgeBase(concepts=tuple(unique))


def _concept(
    concept_id: str,
    zh: str,
    en: str,
    category: KeywordCategory,
    *,
    aliases_zh: list[str] | None = None,
    aliases_en: list[str] | None = None,
    relations: list[ConceptRelation] | None = None,
    enabled: bool = True,
) -> KeywordConcept:
    zh_aliases, en_aliases = aliases_zh or [], aliases_en or []
    return KeywordConcept(
        id=concept_id,
        canonical={"zh": zh, "en": en},
        aliases={"zh": zh_aliases, "en": en_aliases},
        category=category,
        search_terms={"zh": [zh, *zh_aliases], "en": [en, *en_aliases]},
        related_concepts=relations or [],
        applicable_personas=[],
        applicable_platforms=[],
        embedding_text=" ".join([zh, en, *zh_aliases, *en_aliases]),
        enabled=enabled,
        version=1,
    )


KEYWORD_CONCEPTS = (
    _concept("subject_cat", "猫", "cat", "subject", aliases_zh=["猫咪"], aliases_en=["kitty"]),
    _concept(
        "subject_person", "人物", "people", "subject", aliases_zh=["人像"], aliases_en=["person"]
    ),
    _concept("subject_technology", "科技", "technology", "subject", aliases_en=["tech"]),
    _concept(
        "scene_coffee_shop",
        "咖啡店",
        "coffee shop",
        "scene",
        aliases_zh=["咖啡馆"],
        aliases_en=["cafe"],
        relations=[ConceptRelation(concept_id="color_warm", relation="modifier", weight=0.55)],
    ),
    _concept(
        "scene_city",
        "城市",
        "city",
        "scene",
        aliases_en=["urban"],
        relations=[ConceptRelation(concept_id="scene_night", relation="associated", weight=0.4)],
    ),
    _concept(
        "scene_night", "夜晚", "night", "scene", aliases_zh=["夜景"], aliases_en=["nighttime"]
    ),
    _concept(
        "color_warm",
        "暖色",
        "warm lighting",
        "color",
        aliases_zh=["暖色调"],
        aliases_en=["warm tones"],
    ),
    _concept(
        "color_monochrome",
        "黑白",
        "black and white",
        "color",
        aliases_zh=["单色"],
        aliases_en=["monochrome"],
    ),
    _concept("style_minimal", "极简", "minimal", "style", aliases_en=["minimalist"]),
    _concept("style_vintage", "复古", "vintage", "style", aliases_en=["retro"]),
    _concept("style_oil_painting", "油画", "oil painting", "style", aliases_en=["oil painted"]),
    _concept("style_cyberpunk", "赛博朋克", "cyberpunk", "style"),
    _concept(
        "composition_poster",
        "海报",
        "poster",
        "composition",
        aliases_zh=["宣传海报"],
        aliases_en=["poster layout"],
        relations=[ConceptRelation(concept_id="quality_high", relation="modifier", weight=0.5)],
    ),
    _concept(
        "composition_top_view",
        "俯视",
        "top view",
        "composition",
        aliases_zh=["鸟瞰"],
        aliases_en=["overhead view"],
    ),
    _concept(
        "quality_high",
        "高质量",
        "high quality",
        "quality_modifier",
        aliases_zh=["高清"],
        aliases_en=["high resolution"],
    ),
    _concept(
        "quality_professional",
        "专业",
        "professional",
        "quality_modifier",
        aliases_zh=["专业级"],
        aliases_en=["professional grade"],
    ),
    _concept(
        "general_inspiration",
        "灵感",
        "inspiration",
        "general",
        aliases_zh=["创意灵感"],
        aliases_en=["creative inspiration"],
    ),
    _concept(
        "general_reference",
        "参考",
        "reference",
        "general",
        aliases_zh=["素材参考"],
        aliases_en=["visual reference"],
    ),
    _concept("general_disabled_demo", "停用示例", "disabled example", "general", enabled=False),
)

KEYWORD_KNOWLEDGE_BASE = build_knowledge_base(KEYWORD_CONCEPTS)

PLATFORM_RULES = [
    {
        "id": "unsplash",
        "platform": "unsplash",
        "preference": "偏好自然、生活方式和摄影表达",
        "template": "{query}",
    },
    {
        "id": "pexels",
        "platform": "pexels",
        "preference": "偏好商业素材、人物和场景表达",
        "template": "{query}",
    },
    {
        "id": "pixabay",
        "platform": "pixabay",
        "preference": "偏好插画、概念和通用素材表达",
        "template": "{query}",
    },
]
