from app.data.keyword_knowledge import KEYWORDS, PERSONA_RULES, PLATFORM_RULES
from app.providers import EmbeddingProvider, MockEmbeddingProvider


class KeywordRetriever:
    def __init__(self, embedding_provider: EmbeddingProvider | None = None):
        self.embedding_provider = embedding_provider or MockEmbeddingProvider()

    def retrieve(self, query: str, persona: str | None = None, platforms: list[str] | None = None) -> dict[str, list[dict]]:
        try:
            self.embedding_provider.embed([query])
        except Exception:
            pass
        q = query.lower()
        keywords = []
        for item in KEYWORDS:
            if any(term.lower() in q for term in [item["keyword"], *item["aliases"]]):
                keywords.append({"text": item["keyword"], "category": item["category"], "source_type": "keyword", "source_id": item["id"], "score": 0.82, "reason": f"与用户描述中的{item['aliases'][0]}相关"})
        persona_rules = []
        for item in PERSONA_RULES:
            if persona == item["persona"] or any(term.lower() in q for term in item["terms"]):
                persona_rules.append({"text": item["rule"], "category": "persona", "source_type": "persona_rule", "source_id": item["id"], "score": 0.8, "reason": "匹配用户角色规则"})
        allowed = set(platforms or [p["platform"] for p in PLATFORM_RULES])
        platform_rules = [{"text": item["preference"], "category": "platform", "source_type": "platform_rule", "source_id": item["id"], "score": 0.75, "reason": "匹配目标平台偏好"} for item in PLATFORM_RULES if item["platform"] in allowed]
        return {"keywords": keywords, "persona_rules": persona_rules, "platform_rules": platform_rules}


class ContextBuilder:
    def build(self, original_query: str, persona: str | None, retrieved: dict) -> str:
        return "\n".join(["受控关键词优化上下文", f"原始描述：{original_query}", f"用户角色：{persona or '未指定'}", f"检索关键词：{retrieved['keywords']}", f"角色规则：{retrieved['persona_rules']}", f"平台规则：{retrieved['platform_rules']}", "约束：保留原始语义；区分原始关键词和衍生关键词；按主体、场景、颜色、风格、构图分类；不添加无关对象；输出结构化 JSON；平台 query 可以不同但不能改变原始意图。"])
