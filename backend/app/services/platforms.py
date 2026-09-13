from pathlib import Path
from typing import Literal
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, model_validator

PersonaId = Literal[
    "graphic_designer", "illustrator", "photographer", "ecommerce_worker", "ui_designer"
]
CopyrightStatus = Literal[
    "inspiration_only",
    "license_per_item",
    "attribution_required",
    "broad_reuse_license",
    "commercial_license",
    "unknown",
]


class TermRule(BaseModel):
    action: str
    terms: list[str]
    reason: str


class QueryPolicy(BaseModel):
    max_terms: int
    separator: str
    language: str
    include_core_terms: bool
    include_expanded_terms: bool
    include_platform_terms: bool


class PlatformConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    homepage_url: str
    strengths: list[str]
    weaknesses: list[str]
    supported_languages: list[str]
    preferred_categories: list[str]
    term_rules: list[TermRule]
    query_policy: QueryPolicy
    persona_priorities: dict[PersonaId, int]
    recommendation_reason: str
    supports_search_url: bool
    interaction_mode: Literal["executable_search", "recommendation_only", "in_site_search"]
    url_template: str | None
    requires_login: bool
    copyright_status: CopyrightStatus
    copyright_notice: str
    enabled: bool
    version: str

    @model_validator(mode="after")
    def validate_search_url(self):
        if self.supports_search_url != (self.url_template is not None):
            raise ValueError("supports_search_url and url_template must agree")
        if self.url_template is not None and self.url_template.count("{query}") != 1:
            raise ValueError("executable URL must contain exactly one query placeholder")
        if self.supports_search_url != (self.interaction_mode == "executable_search"):
            raise ValueError("interaction_mode must reflect URL capability")
        return self


class PlatformCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    config_version: str
    review_status: Literal["pending_user_review", "reviewed"]
    platforms: tuple[PlatformConfig, ...]


def load_platform_catalog() -> PlatformCatalog:
    path = Path(__file__).parents[3] / "shared" / "platforms.json"
    return PlatformCatalog.model_validate_json(path.read_text(encoding="utf-8"))


PLATFORM_CATALOG = load_platform_catalog()
PLATFORMS = PLATFORM_CATALOG.platforms
PLATFORMS_BY_ID = {item.id: item for item in PLATFORMS}


def platforms_for_persona(persona: str | None) -> list[PlatformConfig]:
    enabled = [item for item in PLATFORMS if item.enabled]
    if not persona:
        return enabled[:7]
    return sorted(
        enabled,
        key=lambda item: (item.persona_priorities.get(persona, 10_000), item.id),
    )[:7]


def build_platform_query(
    config: PlatformConfig,
    core_terms: list[str],
    expanded_terms: list[str],
    language: str = "auto",
) -> str:
    policy = config.query_policy
    terms: list[str] = []
    # A platform may choose its preferred language, while an explicit supported
    # request takes precedence; this changes expression only, never core terms.
    if policy.include_core_terms:
        terms.extend(core_terms)
    if policy.include_expanded_terms:
        terms.extend(expanded_terms)
    if policy.include_platform_terms:
        for rule in config.term_rules:
            if rule.action in {"add", "replace", "filter"}:
                terms.extend(rule.terms)
    result = []
    for term in terms:
        if term and term.casefold() not in {value.casefold() for value in result}:
            result.append(term)
    return policy.separator.join(result[:policy.max_terms])


def build_platform_url(config: PlatformConfig, terms: str) -> str | None:
    if not config.supports_search_url or config.url_template is None:
        return None
    return config.url_template.replace("{query}", quote(terms, safe=""))


def platform_term_id(platform: str, index: int) -> str:
    return f"platform:{platform}:{index}"
