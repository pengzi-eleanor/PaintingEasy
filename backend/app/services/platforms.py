import json
from pathlib import Path
from urllib.parse import quote

from pydantic import BaseModel


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
    id: str
    name: str
    strengths: list[str]
    weaknesses: list[str]
    supported_languages: list[str]
    preferred_categories: list[str]
    term_rules: list[TermRule]
    query_policy: QueryPolicy
    url_template: str
    requires_login: bool
    enabled: bool
    version: str


def load_platforms() -> tuple[PlatformConfig, ...]:
    path = Path(__file__).parents[3] / "shared" / "platforms.json"
    return tuple(PlatformConfig.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8")))


PLATFORMS = load_platforms()
PLATFORMS_BY_ID = {item.id: item for item in PLATFORMS}


def build_platform_query(config: PlatformConfig, core_terms: list[str], expanded_terms: list[str], language: str = "auto") -> str:
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


def build_platform_url(config: PlatformConfig, terms: str) -> str:
    return config.url_template.replace("{query}", quote(terms, safe=""))


def platform_term_id(platform: str, index: int) -> str:
    return f"platform:{platform}:{index}"
