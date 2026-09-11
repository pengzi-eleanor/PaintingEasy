import json

from app.data.keyword_knowledge import KEYWORD_KNOWLEDGE_BASE, PLATFORM_RULES
from app.data.persona_rules import PERSONAS, PersonaProfile
from app.knowledge.orchestrator import ExternalKnowledgeOrchestrator
from app.knowledge.providers import KnowledgeExpansionProvider, LocalKnowledgeExpansionProvider
from app.models.schemas import KnowledgeExpansionContext, KnowledgeExpansionRequest
from app.providers import EmbeddingProvider


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
            weight = profile.category_weights[item["category"]]
            adjusted = {**item, "score": round(min(item["score"] * weight, 1), 4)}
            adjusted["reason"] = (
                f"{item['reason']}；适合{profile.name.zh[0]}，按分类权重排序"
            )
            adjusted["_position"] = position
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
    def __init__(
        self,
        embedding_provider: EmbeddingProvider | None = None,
        knowledge_base=None,
        expansion_provider: KnowledgeExpansionProvider | None = None,
        external_orchestrator: ExternalKnowledgeOrchestrator | None = None,
        use_local_knowledge: bool = False,
    ):
        # The finite concept table is opt-in for historical tests and offline tools only.
        self.embedding_provider = embedding_provider
        self.knowledge_base = knowledge_base or KEYWORD_KNOWLEDGE_BASE
        self.use_local_knowledge = (
            use_local_knowledge or expansion_provider is not None or knowledge_base is not None
        )
        self.expansion_provider = expansion_provider
        if self.use_local_knowledge and self.expansion_provider is None:
            self.expansion_provider = LocalKnowledgeExpansionProvider(self.knowledge_base)
        self.external_orchestrator = external_orchestrator
        self.embedding_degraded = False
        self.external_warnings: list[str] = []

    def retrieve(
        self,
        query: str,
        persona: str | None = None,
        platforms: list[str] | None = None,
        network_expansion: bool = True,
    ) -> dict[str, list[dict]]:
        self.embedding_degraded = False
        self.external_warnings = []
        if self.embedding_provider is not None:
            try:
                self.embedding_provider.embed([query])
            except Exception:
                self.embedding_degraded = True
        request = KnowledgeExpansionRequest(
            query=query,
            language="auto",
            context=KnowledgeExpansionContext(persona=persona, platforms=platforms or []),
        )
        keywords = []
        source_statuses = []
        if self.use_local_knowledge and self.expansion_provider is not None:
            try:
                local_result = self.expansion_provider.expand(request)
            except Exception:
                if self.expansion_provider.name == "tencent_word2vec":
                    local_result = None
                    self.external_warnings = ["本地词向量不可用，已保留原始查询"]
                else:
                    local_result = LocalKnowledgeExpansionProvider(self.knowledge_base).expand(
                        request
                    )
                    self.external_warnings = ["离线知识扩展不可用，已回退到历史概念表"]
            if local_result is None:
                local_candidates = []
            else:
                local_candidates = local_result.candidates
            keywords.extend(
                {
                    "text": item.term,
                    "category": item.category,
                    "source_type": (
                        item.source
                        if item.source == "tencent_word2vec"
                        else "keyword"
                        if item.relation == "exact"
                        else "concept_relation"
                    ),
                    "source_id": item.source_id,
                    "score": item.confidence,
                    "reason": item.reason,
                    "group": "core" if item.relation == "exact" else "expanded",
                }
                for item in local_candidates
            )
            if local_result is not None:
                source_statuses.append(
                    {
                        "source": (
                            "local_rules"
                            if local_result.provider == "local_rule"
                            else local_result.provider
                        ),
                        "status": local_result.source_status,
                        "message": local_result.warning or "本地知识扩展",
                    }
                )
        seen = {item["text"].casefold() for item in keywords}
        if self.external_orchestrator is not None and network_expansion:
            external_results, warnings = self.external_orchestrator.expand(request)
            self.external_warnings.extend(warnings)
            for result in external_results:
                source_statuses.append(
                    {
                        "source": result.provider,
                        "status": result.source_status,
                        "message": result.warning or "",
                    }
                )
                for item in result.candidates:
                    if item.term.casefold() in seen:
                        continue
                    seen.add(item.term.casefold())
                    keywords.append(
                        {
                            "text": item.term,
                            "category": item.category,
                            "source_type": item.source,
                            "source_id": item.source_id,
                            "score": item.confidence,
                            "reason": item.reason,
                            "group": "expanded",
                        }
                    )
        else:
            configured_providers = (
                [
                    provider.name
                    for provider in self.external_orchestrator.providers
                    if provider.enabled
                ]
                if self.external_orchestrator is not None
                else ["wikidata"]
            )
            source_statuses.extend(
                [
                    {
                        "source": provider,
                        "status": "original_fallback",
                        "message": (
                            "用户已关闭网络知识扩展"
                            if self.external_orchestrator is not None
                            else "外部知识源尚未启用"
                        ),
                    }
                    for provider in configured_providers
                ]
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
        allowed = set(platforms or [p["platform"] for p in PLATFORM_RULES])
        platform_rules = [
            {
                "text": item["preference"],
                "category": "platform",
                "source_type": "platform_rule",
                "source_id": item["id"],
                "score": 0.75,
                "reason": "匹配目标平台偏好",
            }
            for item in PLATFORM_RULES
            if item["platform"] in allowed
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
