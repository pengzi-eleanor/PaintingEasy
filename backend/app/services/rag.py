from app.data.keyword_knowledge import KEYWORD_KNOWLEDGE_BASE, PLATFORM_RULES
from app.data.persona_rules import PERSONAS, PersonaProfile
from app.providers import EmbeddingProvider, MockEmbeddingProvider


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
                f"{item['reason']}；{profile.name.zh[0]}按{item['category']}分类权重"
                f"{weight:.2f}调整排序"
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
                    "reason": f"{profile.name.zh[0]}条件命中：{modifier.reason}",
                    "_position": len(ranked),
                }
            )

        ranked.sort(key=lambda item: (-item["score"], item["_position"], item["source_id"]))
        for item in ranked:
            item.pop("_position")
        return ranked, profile


class KeywordRetriever:
    def __init__(self, embedding_provider: EmbeddingProvider | None = None, knowledge_base=None):
        # Embedding is opt-in; default retrieval is explicitly rules-only.
        self.embedding_provider = embedding_provider
        self.knowledge_base = knowledge_base or KEYWORD_KNOWLEDGE_BASE
        self.embedding_degraded = False

    def retrieve(
        self, query: str, persona: str | None = None, platforms: list[str] | None = None
    ) -> dict[str, list[dict]]:
        if self.embedding_provider is not None:
            try:
                self.embedding_provider.embed([query])
            except Exception:
                self.embedding_degraded = True
        q = query.lower()
        keywords = []
        seen: set[str] = set()
        direct_matches = []
        for concept in self.knowledge_base.concepts:
            if not concept.enabled or concept.id in seen:
                continue
            matched = next((term for term in concept.match_terms() if term.casefold() in q), None)
            if matched is not None:
                seen.add(concept.id)
                direct_matches.append(concept)
                keywords.append(
                    {
                        "text": concept.canonical.en,
                        "category": concept.category,
                        "source_type": "keyword",
                        "source_id": concept.id,
                        "score": 0.82,
                        "reason": f"与用户描述中的{matched}相关",
                    }
                )
        by_id = self.knowledge_base.by_id
        for source in direct_matches:
            for relation in source.related_concepts:
                target = by_id[relation.concept_id]
                # Subjects may only enter results through direct matching.
                if not target.enabled or target.id in seen or target.category == "subject":
                    continue
                seen.add(target.id)
                keywords.append(
                    {
                        "text": target.canonical.en,
                        "category": target.category,
                        "source_type": "concept_relation",
                        "source_id": target.id,
                        "score": round(0.82 * relation.weight, 4),
                        "reason": f"由{source.canonical.zh}的{relation.relation}关系扩展",
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
        }


class ContextBuilder:
    def build(self, original_query: str, persona: str | None, retrieved: dict) -> str:
        return "\n".join(
            [
                "受控关键词优化上下文",
                f"原始描述：{original_query}",
                f"用户角色：{persona or '未指定'}",
                f"检索关键词：{retrieved['keywords']}",
                f"角色规则：{retrieved['persona_rules']}",
                f"平台规则：{retrieved['platform_rules']}",
                "约束：保留原始语义；区分原始关键词和衍生关键词；"
                "按主体、场景、颜色、风格、构图分类；不添加无关对象；"
                "输出结构化 JSON；平台 query 可以不同但不能改变原始意图。",
            ]
        )
