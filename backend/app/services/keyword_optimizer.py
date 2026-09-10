import re
from hashlib import sha1
from typing import Protocol

from app.models.schemas import KeywordCandidate, KeywordSuggestion, PlatformQuery, ScoreBreakdown, SearchAssistResponse
from app.models.schemas import MockKeywordOutput
from app.providers import LanguageModelProvider, MockLanguageModelProvider
from app.services.rag import ContextBuilder, KeywordRetriever
from app.services.platforms import PLATFORMS, build_platform_query, build_platform_url, platform_term_id


class KeywordSuggestionProvider(Protocol):
    def suggest(self, query: str) -> list[KeywordSuggestion]: ...


class RuleBasedKeywordSuggestionProvider:
    """Deterministic dictionary/rule provider; deliberately makes no external calls."""

    DICTIONARY = {
        "赛博朋克": ("cyberpunk", "style"), "油画": ("oil painting", "style"),
        "黑白": ("black and white", "color"), "复古": ("vintage", "style"),
        "极简": ("minimal", "style"), "猫": ("cat", "subject"), "狗": ("dog", "subject"),
        "人像": ("portrait", "subject"), "女孩": ("girl", "subject"), "男孩": ("boy", "subject"),
        "风景": ("landscape", "scene"), "城市": ("city", "scene"), "科技": ("technology", "subject"),
        "商务": ("business", "subject"), "水彩": ("watercolor", "style"), "咖啡": ("coffee", "subject"),
    }
    ENGLISH_CATEGORIES = {"night": "scene", "vintage": "style", "cyberpunk": "style",
                          "cat": "subject", "dog": "subject", "portrait": "subject",
                          "landscape": "scene", "city": "scene", "quality": "quality"}

    def suggest(self, query: str) -> list[KeywordSuggestion]:
        found: list[KeywordSuggestion] = []
        seen: set[str] = set()
        remaining = query.lower()
        for source, (keyword, category) in sorted(self.DICTIONARY.items(), key=lambda x: -len(x[0])):
            if source in query and keyword not in seen:
                seen.add(keyword)
                found.append(KeywordSuggestion(keyword=keyword, category=category, source="dictionary",
                    confidence=0.9 if len(source) > 1 else 0.95,
                    reason=f"从中文“{source}”映射为英文{category}关键词"))
                remaining = remaining.replace(source.lower(), " ")
        for phrase in re.findall(r"\b(?:oil\s+painting|black\s+and\s+white)\b", remaining):
            keyword = re.sub(r"\s+", " ", phrase.lower()).strip()
            if keyword not in seen:
                seen.add(keyword)
                found.append(KeywordSuggestion(keyword=keyword, category="style" if keyword == "oil painting" else "color",
                    source="rule", confidence=0.88, reason="识别英文复合检索词并规范化"))
                remaining = remaining.replace(phrase, " ")
        for token in re.findall(r"[a-zA-Z]+(?:[-'][a-zA-Z]+)?", remaining):
            keyword = token.lower()
            if keyword not in seen:
                seen.add(keyword)
                found.append(KeywordSuggestion(keyword=keyword,
                    category=self.ENGLISH_CATEGORIES.get(keyword, "general"), selected=True,
                    source="rule", confidence=0.82, reason="从原始查询中提取并规范化英文关键词"))
        return found


class KeywordOptimizeService:
    def __init__(self, provider: KeywordSuggestionProvider | None = None, retriever=None, llm_provider: LanguageModelProvider | None = None):
        self.provider = provider or RuleBasedKeywordSuggestionProvider()
        self.retriever = retriever or KeywordRetriever()
        self.llm_provider = llm_provider or MockLanguageModelProvider()

    @staticmethod
    def _candidate(item: KeywordSuggestion, index: int, original_query: str) -> KeywordCandidate:
        group = "expanded" if item.source == "mock" or item.group == "expanded" else item.group
        source = "llm" if item.source == "mock" else item.source
        if "原始查询" in item.reason:
            source, group = "original", "core"
        if source not in {"dictionary", "rule", "fallback", "llm", "embedding", "original"}:
            source = "rule"
        exact = 1.0 if item.keyword.casefold() in original_query.casefold() else 0.0
        semantic = item.confidence
        relation = 0.7 if group == "expanded" else 0.0
        final = round(exact * .35 + semantic * .2 + relation * .15, 6)
        return KeywordCandidate(id=f"kw_{sha1(f'{index}:{item.keyword}'.encode()).hexdigest()[:12]}",
            concept_id=item.keyword.casefold().replace(" ", "_"), keyword=item.keyword,
            display_keyword=item.keyword, language="zh" if re.search(r"[\u4e00-\u9fff]", item.keyword) else "en",
            category=item.category, group=group, source=source, selected=item.selected,
            removable=True, scores=ScoreBreakdown(exact_match=exact, semantic_similarity=semantic,
                relation_weight=relation, persona_weight=0, platform_weight=0, final_score=final),
            reason=item.reason or "保留原始语义", derived_from=[] if source == "original" else [original_query],
            applicable_platforms=[])

    def optimize(self, original_query: str, persona: str | None = None, platforms: list[str] | None = None, language: str = "auto") -> SearchAssistResponse:
        original_query = original_query.strip()
        if not original_query:
            return SearchAssistResponse(original_query="", query="", suggestions=[], platforms=[],
                degraded=True, messages=["请输入搜索内容后再获取关键词建议"])
        degraded = False
        messages: list[str] = []
        try:
            suggestions = self.provider.suggest(original_query)
        except Exception:
            suggestions = []
            degraded = True
            messages.append("关键词 provider 暂不可用，已降级为基础搜索")
        retrieved = self.retriever.retrieve(original_query, persona, platforms)
        if getattr(self.retriever, "embedding_degraded", False):
            degraded = True
            messages.append("Embedding provider 暂不可用，已回退到规则检索")
        existing = {item.keyword.lower() for item in suggestions}
        for item in retrieved["keywords"]:
            if item["text"].lower() not in existing:
                suggestions.append(KeywordSuggestion(keyword=item["text"], category=item["category"], source="dictionary", confidence=item["score"], reason=item["reason"]))
                existing.add(item["text"].lower())
        try:
            context = ContextBuilder().build(original_query, persona, retrieved)
            output = MockKeywordOutput.model_validate(self.llm_provider.generate_keywords(context))
            for item in output.derived_terms:
                if item.keyword.lower() not in existing:
                    suggestions.append(KeywordSuggestion(**item.model_dump()))
                    existing.add(item.keyword.lower())
        except Exception:
            degraded = True
            messages.append("语言模型 provider 暂不可用或返回格式无效，已降级为规则和检索结果")
        if re.search(r"[a-zA-Z]", original_query) and not re.search(r"[\u4e00-\u9fff]", original_query):
            suggestions.sort(key=lambda item: original_query.lower().find(item.keyword.lower()))
        if not suggestions:
            safe_query = " ".join(re.findall(r"[a-zA-Z0-9]+", original_query)).strip() or original_query
            suggestions = [KeywordSuggestion(keyword=safe_query, category="general", source="fallback",
                confidence=0.25, reason="未识别到可映射关键词，保留安全搜索片段")]
            degraded = True
            if not messages:
                messages.append("未识别到关键词，已使用基础搜索降级")
        query = " ".join(item.keyword for item in suggestions)
        selected_platforms = [item for item in PLATFORMS if item.enabled and (not platforms or item.id in platforms)]
        selected_platforms = selected_platforms or [item for item in PLATFORMS if item.enabled]
        core = [item.keyword for item in suggestions if item.group == "core"]
        expanded = [item.keyword for item in suggestions if item.group != "core"]
        candidates = [self._candidate(item, index, original_query) for index, item in enumerate(suggestions)]
        platform_links: list[PlatformQuery] = []
        for config in selected_platforms:
            platform_query = build_platform_query(config, core, expanded, language)
            terms = platform_query.split(config.query_policy.separator) if platform_query else []
            core_ids = [candidate.id for candidate in candidates if candidate.group == "core" and candidate.selected]
            expanded_ids = [candidate.id for candidate in candidates if candidate.keyword in terms and candidate.group == "expanded"]
            platform_ids = [platform_term_id(config.id, index) for index, term in enumerate(terms) if term in {rule_term for rule in config.term_rules for rule_term in rule.terms}]
            reasons = [f"保留核心词 {len(core_ids)} 个"]
            reasons.extend(f"采用：{rule.reason}" for rule in config.term_rules if any(term in terms for term in rule.terms))
            score = round(min(1, 0.5 + 0.05 * len(core_ids) + 0.03 * len(expanded_ids)), 6)
            platform_links.append(PlatformQuery(platform=config.id, name=config.name, query=platform_query,
                terms=terms, core_term_ids=core_ids, expanded_term_ids=expanded_ids, platform_term_ids=platform_ids,
                url=build_platform_url(config, platform_query), requires_login=config.requires_login, score=score, reasons=reasons))
        core_candidates = [item for item in candidates if item.group == "core"]
        expanded_candidates = [item for item in candidates if item.group == "expanded"]
        retrieval_degraded = bool(getattr(self.retriever, "embedding_degraded", False)) or degraded
        embedding_active = getattr(self.retriever, "embedding_provider", None) is not None
        strategy = "fallback" if not candidates else ("hybrid" if embedding_active and not getattr(self.retriever, "embedding_degraded", False) else "rules_only")
        retrieval = {"strategy": strategy, "embedding_enabled": strategy == "hybrid", "embedding_provider": "mock" if strategy == "hybrid" else "none", "embedding_model": "deterministic-mock" if strategy == "hybrid" else "none", "knowledge_base_version": "keyword-knowledge-v1", "candidate_count": len(candidates), "degraded": retrieval_degraded}
        return SearchAssistResponse(original_query=original_query, query=query, suggestions=candidates,
            platforms=platform_links, core_terms=core_candidates, expanded_terms=expanded_candidates,
            platform_terms=[], default_query=query, platform_queries=platform_links, retrieval=retrieval,
            degraded=degraded, messages=messages, warnings=messages)
