import json

from app.data.persona_rules import PERSONAS, PersonaProfile
from app.knowledge.providers import KnowledgeExpansionProvider
from app.models.schemas import KnowledgeExpansionContext, KnowledgeExpansionRequest
from app.services.platforms import PLATFORMS


class PersonaRuleEngine:
    """Apply validated persona ranking and conditional modifiers without changing subjects."""

    def apply(
        self, query: str, keywords: list[dict], persona: str | None
    ) -> tuple[list[dict], PersonaProfile | None]:
        profile = PERSONAS.get(persona) if persona else None
        if profile is None:
            return keywords, None
        ranked: list[dict] = []
        blocked = set(profile.blocked_expansions)
        for position, item in enumerate(keywords):
            if item["source_type"] != "keyword" and item["source_id"] in blocked:
                continue
            adjusted = {
                **item,
                "score": round(
                    min(item["score"] * profile.category_weights[item["category"]], 1), 4
                ),
                "reason": f"{item['reason']}；适合{profile.name.zh[0]}，按分类权重排序",
                "_position": position,
            }
            ranked.append(adjusted)
        existing = {item["text"].casefold() for item in ranked}
        for modifier in profile.preferred_modifiers:
            if modifier.keyword.casefold() in existing or not modifier.condition.matches(query):
                continue
            existing.add(modifier.keyword.casefold())
            ranked.append(
                {
                    "text": modifier.keyword,
                    "category": modifier.category,
                    "source_type": "persona_modifier",
                    "source_id": modifier.id,
                    "score": modifier.weight,
                    "reason": modifier.reason,
                    "group": "expanded",
                    "_position": len(ranked),
                }
            )
        ranked.sort(key=lambda item: (-item["score"], item["_position"], item["source_id"]))
        for item in ranked:
            item.pop("_position")
        return ranked, profile


class KeywordRetriever:
    def __init__(self, expansion_provider: KnowledgeExpansionProvider | None = None):
        self.expansion_provider = expansion_provider
        self.provider_degraded = False
        self.warnings: list[str] = []

    @property
    def provider_name(self) -> str | None:
        return self.expansion_provider.name if self.expansion_provider else None

    def retrieve(
        self,
        query: str,
        persona: str | None = None,
        platforms: list[str] | None = None,
        network_expansion: bool = True,
    ) -> dict[str, list[dict]]:
        # network_expansion is retained only for backward API compatibility.
        self.provider_degraded = False
        self.warnings = []
        request = KnowledgeExpansionRequest(
            query=query,
            language="auto",
            context=KnowledgeExpansionContext(persona=persona, platforms=platforms or []),
        )
        keywords: list[dict] = []
        source_statuses: list[dict] = []
        if self.expansion_provider is not None:
            try:
                result = self.expansion_provider.expand(request)
                keywords.extend(
                    {
                        "text": item.term,
                        "category": item.category,
                        "source_type": item.source,
                        "source_id": item.source_id,
                        "score": item.confidence,
                        "reason": item.reason,
                        "group": "expanded",
                    }
                    for item in result.candidates
                )
                source_statuses.append(
                    {
                        "source": "tencent_word2vec",
                        "status": result.source_status,
                        "message": result.warning or "本地中文词向量",
                    }
                )
            except Exception:
                self.provider_degraded = True
                self.warnings.append("本地词向量不可用，已保留原始查询")
                source_statuses.append(
                    {
                        "source": "tencent_word2vec",
                        "status": "original_fallback",
                        "message": "本地词向量不可用",
                    }
                )
        keywords, profile = PersonaRuleEngine().apply(query, keywords, persona)
        persona_rules = (
            []
            if profile is None
            else [
                {
                    "text": profile.prompt_context,
                    "category": "persona",
                    "source_type": "persona_rule",
                    "source_id": profile.id,
                    "score": 0.8,
                    "reason": f"已选择{profile.name.zh[0]}职业规则",
                }
            ]
        )
        allowed = set(platforms or [item.id for item in PLATFORMS if item.enabled])
        platform_rules = [
            {
                "text": item.recommendation_reason,
                "category": "platform",
                "source_type": "platform_rule",
                "source_id": item.id,
                "score": 0.75,
                "reason": "匹配目标平台偏好",
            }
            for item in PLATFORMS
            if item.enabled and item.id in allowed
        ]
        if profile is not None:
            priority = {platform: index for index, platform in enumerate(profile.platform_priority)}
            platform_rules.sort(key=lambda item: priority.get(item["source_id"], len(priority)))
        return {
            "keywords": keywords,
            "persona_rules": persona_rules,
            "platform_rules": platform_rules,
            "knowledge_sources": source_statuses,
        }


class ContextBuilder:
    def build(
        self,
        original_query: str,
        persona: str | None,
        retrieved: dict,
        *,
        language: str = "auto",
        allowed_platforms: list[dict] | None = None,
    ) -> str:
        profile = PERSONAS.get(persona) if persona else None
        payload = {
            "original_description": original_query,
            "language": language,
            "persona_context": profile.prompt_context if profile else "未指定职业",
            "knowledge_candidates": [
                {
                    "term": item["text"],
                    "category": item["category"],
                    "reason": item["reason"],
                }
                for item in retrieved["keywords"]
            ],
            "allowed_platforms": allowed_platforms or [],
            "limits": {"core_terms": 6, "expanded_terms": 8, "platform_plans": 5},
            "instructions": {
                "preserve_original_intent": True,
                "do_not_invent_subjects": True,
                "return_structured_json_only": True,
                "do_not_return_urls": True,
            },
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
