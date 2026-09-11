import re
from hashlib import sha1
from typing import Protocol

from app.models.schemas import (
    GenerationStatus,
    KeywordCandidate,
    KeywordSuggestion,
    KnowledgeSourceStatus,
    OptimizationMode,
    PlatformQuery,
    PlatformRecommendation,
    ScoreBreakdown,
    SearchAssistResponse,
    SmartOptimizationOutput,
)
from app.providers import (
    InMemoryUsageQuota,
    LanguageModelProvider,
    MockLanguageModelProvider,
    QuotaExceededError,
)
from app.services.platforms import (
    PLATFORMS,
    build_platform_query,
    build_platform_url,
    platform_term_id,
    platforms_for_persona,
)
from app.services.rag import ContextBuilder, KeywordRetriever


class KeywordSuggestionProvider(Protocol):
    def suggest(self, query: str) -> list[KeywordSuggestion]: ...


class RuleBasedKeywordSuggestionProvider:
    """Deterministic dictionary/rule provider; deliberately makes no external calls."""

    DICTIONARY = {
        "赛博朋克": ("cyberpunk", "style"),
        "油画": ("oil painting", "style"),
        "黑白": ("black and white", "color"),
        "复古": ("vintage", "style"),
        "极简": ("minimal", "style"),
        "猫": ("cat", "subject"),
        "狗": ("dog", "subject"),
        "人像": ("portrait", "subject"),
        "女孩": ("girl", "subject"),
        "男孩": ("boy", "subject"),
        "风景": ("landscape", "scene"),
        "城市": ("city", "scene"),
        "科技": ("technology", "subject"),
        "商务": ("business", "subject"),
        "水彩": ("watercolor", "style"),
        "咖啡": ("coffee", "subject"),
    }
    ENGLISH_CATEGORIES = {
        "night": "scene",
        "vintage": "style",
        "cyberpunk": "style",
        "cat": "subject",
        "dog": "subject",
        "portrait": "subject",
        "landscape": "scene",
        "city": "scene",
        "quality": "quality",
    }

    def suggest(self, query: str) -> list[KeywordSuggestion]:
        category_labels = {
            "subject": "主体",
            "scene": "场景",
            "style": "风格",
            "color": "色彩",
            "composition": "构图",
            "general": "通用",
        }
        found: list[KeywordSuggestion] = []
        seen: set[str] = set()
        remaining = query.lower()
        for source, (keyword, category) in sorted(
            self.DICTIONARY.items(), key=lambda x: -len(x[0])
        ):
            if source in query and keyword not in seen:
                seen.add(keyword)
                found.append(
                    KeywordSuggestion(
                        keyword=keyword,
                        category=category,
                        source="dictionary",
                        confidence=0.9 if len(source) > 1 else 0.95,
                        reason=f"将“{source}”转换为英文{category_labels.get(category, '检索')}词",
                    )
                )
                remaining = remaining.replace(source.lower(), " ")
        for phrase in re.findall(r"\b(?:oil\s+painting|black\s+and\s+white)\b", remaining):
            keyword = re.sub(r"\s+", " ", phrase.lower()).strip()
            if keyword not in seen:
                seen.add(keyword)
                found.append(
                    KeywordSuggestion(
                        keyword=keyword,
                        category="style" if keyword == "oil painting" else "color",
                        source="rule",
                        confidence=0.88,
                        reason="识别英文复合检索词并规范化",
                    )
                )
                remaining = remaining.replace(phrase, " ")
        for token in re.findall(r"[a-zA-Z]+(?:[-'][a-zA-Z]+)?", remaining):
            keyword = token.lower()
            if keyword not in seen:
                seen.add(keyword)
                found.append(
                    KeywordSuggestion(
                        keyword=keyword,
                        category=self.ENGLISH_CATEGORIES.get(keyword, "general"),
                        selected=True,
                        source="rule",
                        confidence=0.82,
                        reason="从原始查询中提取并规范化英文关键词",
                    )
                )
        return found


class KeywordOptimizeService:
    def __init__(
        self,
        provider: KeywordSuggestionProvider | None = None,
        retriever=None,
        llm_provider: LanguageModelProvider | None = None,
        quota: InMemoryUsageQuota | None = None,
    ):
        self.provider = provider
        self.retriever = retriever or KeywordRetriever()
        self.llm_provider = llm_provider or MockLanguageModelProvider()
        self.quota = quota or InMemoryUsageQuota(20)
        self.context_builder = ContextBuilder()

    @staticmethod
    def _candidate(item: KeywordSuggestion, index: int, original_query: str) -> KeywordCandidate:
        group = "expanded" if item.group == "expanded" else item.group
        source = "llm" if item.source == "mock" else item.source
        if "原始查询" in item.reason:
            source, group = "original", "core"
        if source not in {
            "dictionary",
            "rule",
            "external",
            "fallback",
            "llm",
            "embedding",
            "original",
        }:
            source = "rule"
        exact = 1.0 if item.keyword.casefold() in original_query.casefold() else 0.0
        semantic = item.confidence
        relation = 0.7 if group == "expanded" else 0.0
        final = round(exact * 0.35 + semantic * 0.2 + relation * 0.15, 6)
        return KeywordCandidate(
            id=f"kw_{sha1(f'{index}:{item.keyword}'.encode()).hexdigest()[:12]}",
            concept_id=item.keyword.casefold().replace(" ", "_"),
            keyword=item.keyword,
            display_keyword=item.keyword,
            language="zh" if re.search(r"[\u4e00-\u9fff]", item.keyword) else "en",
            category=item.category,
            group=group,
            source=source,
            selected=item.selected,
            removable=True,
            scores=ScoreBreakdown(
                exact_match=exact,
                semantic_similarity=semantic,
                relation_weight=relation,
                persona_weight=0,
                platform_weight=0,
                final_score=final,
            ),
            reason=item.reason or "保留原始语义",
            derived_from=[] if source == "original" else (item.derived_from or [original_query]),
            applicable_platforms=[],
        )

    def optimize(
        self,
        original_query: str,
        persona: str | None = None,
        platforms: list[str] | None = None,
        language: str = "auto",
        optimization_mode: OptimizationMode = "basic",
        network_expansion: bool = True,
    ) -> SearchAssistResponse:
        original_query = " ".join(original_query.split())
        if not original_query:
            return SearchAssistResponse(
                original_query="",
                query="",
                suggestions=[],
                platforms=[],
                degraded=True,
                messages=["请输入搜索内容后再获取关键词建议"],
                optimization_mode=optimization_mode,
                knowledge_sources=[
                    KnowledgeSourceStatus(source="local_rules", status="live"),
                    KnowledgeSourceStatus(source="wikidata", status="original_fallback"),
                    KnowledgeSourceStatus(source="conceptnet", status="original_fallback"),
                ],
                generation_status=GenerationStatus(
                    status="not_requested" if optimization_mode == "basic" else "not_available",
                    ai_used=False,
                    message="请输入搜索内容后再生成关键词",
                ),
            )
        degraded = False
        messages: list[str] = []
        generation_status = GenerationStatus(
            status="not_requested",
            ai_used=False,
            message="基础优化未调用大模型",
            remaining_uses=self.quota.remaining,
        )
        core_intent_category = "general"
        uncertainties: list[str] = []
        smart_platform_reasons: dict[str, str] = {}
        suggestions = [
            KeywordSuggestion(
                keyword=original_query,
                category="general",
                source="fallback",
                confidence=1,
                reason="保留原始查询",
                group="core",
            )
        ]
        if self.provider is not None:
            try:
                legacy_suggestions = self.provider.suggest(original_query)
                suggestions.extend(
                    item
                    for item in legacy_suggestions
                    if item.keyword.casefold() != original_query.casefold()
                )
            except Exception:
                degraded = True
                messages.append("关键词 provider 暂不可用，已降级为基础搜索")
        retrieved = self.retriever.retrieve(
            original_query, persona, platforms, network_expansion=network_expansion
        )
        if getattr(self.retriever, "embedding_degraded", False):
            degraded = True
            messages.append("Embedding provider 暂不可用，已回退到规则检索")
        if getattr(self.retriever, "external_warnings", None):
            degraded = True
            messages.extend(self.retriever.external_warnings)
        existing = {item.keyword.casefold() for item in suggestions}
        for item in retrieved["keywords"]:
            if item["text"].casefold() not in existing:
                source = (
                    "external"
                    if item["source_type"] in {"wikidata", "conceptnet", "cache"}
                    else "embedding"
                    if item["source_type"] == "tencent_word2vec"
                    else "rule"
                )
                suggestions.append(
                    KeywordSuggestion(
                        keyword=item["text"],
                        category=item["category"],
                        source=source,
                        confidence=item["score"],
                        reason=item["reason"],
                        group=item.get("group", "core"),
                    )
                )
                existing.add(item["text"].casefold())
        ordered_platforms = platforms_for_persona(persona)
        selected_platforms = (
            [item for item in PLATFORMS if item.enabled and item.id in platforms]
            if platforms
            else ordered_platforms
        )
        selected_platforms = selected_platforms or ordered_platforms
        if optimization_mode == "smart":
            basic_suggestions = list(suggestions)
            try:
                remaining = self.quota.consume()
                allowed_platforms = [
                    {"id": item.id, "reason": item.recommendation_reason}
                    for item in selected_platforms
                ]
                prompt = self.context_builder.build(
                    original_query,
                    persona,
                    retrieved,
                    language=language,
                    allowed_platforms=allowed_platforms,
                )
                output = self.llm_provider.generate_keywords(prompt)
                if not isinstance(output, SmartOptimizationOutput):
                    raise ValueError("provider returned an unvalidated response")
                allowed_ids = {item.id for item in selected_platforms}
                if any(item.platform_id not in allowed_ids for item in output.platform_plans):
                    raise ValueError("model selected an unknown platform")
                known_subjects = {
                    item["text"].casefold()
                    for item in retrieved["keywords"]
                    if item["category"] == "subject"
                }
                for item in (*output.core_terms, *output.expanded_terms):
                    if (
                        item.category == "subject"
                        and item.keyword.casefold() not in original_query.casefold()
                        and item.keyword.casefold() not in known_subjects
                    ):
                        raise ValueError("model invented an unsupported subject")
                suggestions = [basic_suggestions[0]]
                existing = {suggestions[0].keyword.casefold()}
                for group, smart_terms in (
                    ("core", output.core_terms),
                    ("expanded", output.expanded_terms),
                ):
                    for item in smart_terms:
                        if (
                            group == "core"
                            and sum(suggestion.group == "core" for suggestion in suggestions) >= 6
                        ):
                            break
                        if item.keyword.casefold() in existing:
                            continue
                        suggestions.append(
                            KeywordSuggestion(
                                keyword=item.keyword,
                                category=item.category,
                                source="mock",
                                confidence=0.8,
                                reason=item.reason,
                                group=group,
                                derived_from=item.derived_from,
                            )
                        )
                        existing.add(item.keyword.casefold())
                if output.platform_plans:
                    by_id = {item.id: item for item in selected_platforms}
                    selected_platforms = [by_id[item.platform_id] for item in output.platform_plans]
                    smart_platform_reasons = {
                        item.platform_id: item.reason for item in output.platform_plans
                    }
                core_intent_category = output.core_intent_category
                uncertainties = output.uncertainties
                generation_status = GenerationStatus(
                    status="generated",
                    ai_used=True,
                    message="智能优化建议已生成，可编辑、拒绝或回退",
                    remaining_uses=remaining,
                )
            except QuotaExceededError:
                suggestions = basic_suggestions
                degraded = True
                messages.append("智能优化额度不足，已回退基础优化")
                generation_status = GenerationStatus(
                    status="fallback",
                    ai_used=False,
                    message="AI 额度不足，已回退基础优化",
                    remaining_uses=0,
                )
            except (TimeoutError, ValueError, RuntimeError):
                suggestions = basic_suggestions
                degraded = True
                messages.append("智能优化不可用，已回退基础优化")
                generation_status = GenerationStatus(
                    status="fallback",
                    ai_used=False,
                    message="AI 输出未通过校验或服务不可用，已回退基础优化",
                    remaining_uses=self.quota.remaining,
                )
        if re.search(r"[a-zA-Z]", original_query) and not re.search(
            r"[\u4e00-\u9fff]", original_query
        ):
            suggestions.sort(
                key=lambda item: (
                    0 if "原始查询" in item.reason else 1,
                    (
                        original_query.casefold().find(item.keyword.casefold())
                        if item.keyword.casefold() in original_query.casefold()
                        else len(original_query)
                    ),
                )
            )
        external_candidates = [
            item for item in suggestions if item.source in {"external", "embedding"}
        ]
        if not external_candidates:
            degraded = True
            messages.append("外部知识源无可用候选，已保留原始查询生成平台搜索")
        query = " ".join(item.keyword for item in suggestions)
        core = [item.keyword for item in suggestions if item.group == "core"]
        expanded = [item.keyword for item in suggestions if item.group != "core"]
        candidates = [
            self._candidate(item, index, original_query) for index, item in enumerate(suggestions)
        ]
        platform_links: list[PlatformQuery] = []
        for config in selected_platforms:
            platform_query = build_platform_query(config, core, expanded, language)
            terms = platform_query.split(config.query_policy.separator) if platform_query else []
            core_ids = [
                candidate.id
                for candidate in candidates
                if candidate.group == "core" and candidate.selected
            ]
            expanded_ids = [
                candidate.id
                for candidate in candidates
                if candidate.keyword in terms and candidate.group == "expanded"
            ]
            platform_ids = [
                platform_term_id(config.id, index)
                for index, term in enumerate(terms)
                if term in {rule_term for rule in config.term_rules for rule_term in rule.terms}
            ]
            reasons = [f"保留核心词 {len(core_ids)} 个"]
            reasons.extend(
                f"采用：{rule.reason}"
                for rule in config.term_rules
                if any(term in terms for term in rule.terms)
            )
            score = round(min(1, 0.5 + 0.05 * len(core_ids) + 0.03 * len(expanded_ids)), 6)
            platform_links.append(
                PlatformQuery(
                    platform=config.id,
                    name=config.name,
                    query=platform_query,
                    terms=terms,
                    core_term_ids=core_ids,
                    expanded_term_ids=expanded_ids,
                    platform_term_ids=platform_ids,
                    url=build_platform_url(config, platform_query) or config.homepage_url,
                    requires_login=config.requires_login,
                    supports_search_url=config.supports_search_url,
                    interaction_mode=config.interaction_mode,
                    copyright_status=config.copyright_status,
                    copyright_notice=config.copyright_notice,
                    recommendation_reason=config.recommendation_reason,
                    config_version=config.version,
                    score=score,
                    reasons=reasons,
                )
            )
        core_candidates = [item for item in candidates if item.group == "core"]
        expanded_candidates = [item for item in candidates if item.group == "expanded"]
        retrieval_degraded = bool(getattr(self.retriever, "embedding_degraded", False)) or degraded
        embedding_active = any(item.source == "embedding" for item in suggestions) or (
            getattr(self.retriever, "embedding_provider", None) is not None
        )
        strategy = (
            "hybrid"
            if external_candidates
            and embedding_active
            and not getattr(self.retriever, "embedding_degraded", False)
            else "external"
            if external_candidates
            else "fallback"
        )
        retrieval = {
            "strategy": strategy,
            "embedding_enabled": strategy == "hybrid",
            "embedding_provider": "tencent_word2vec" if embedding_active else "none",
            "embedding_model": (
                "tencent-ailab-light-143613-d200-v1" if embedding_active else "none"
            ),
            "knowledge_base_version": (
                "tencent-ailab-light-143613-d200-v1"
                if any(item.source == "embedding" for item in suggestions)
                else "external-knowledge-v1"
                if external_candidates
                else "original-fallback-v1"
            ),
            "candidate_count": len(candidates),
            "degraded": retrieval_degraded,
        }
        return SearchAssistResponse(
            original_query=original_query,
            query=query,
            suggestions=candidates,
            platforms=platform_links,
            core_terms=core_candidates,
            expanded_terms=expanded_candidates,
            platform_terms=[],
            default_query=query,
            platform_queries=platform_links,
            retrieval=retrieval,
            degraded=degraded,
            messages=messages,
            warnings=messages,
            optimization_mode=optimization_mode,
            knowledge_sources=[
                KnowledgeSourceStatus.model_validate(item)
                for item in retrieved["knowledge_sources"]
            ],
            platform_recommendations=[
                PlatformRecommendation(
                    platform=item.id,
                    name=item.name,
                    rank=index,
                    reason=smart_platform_reasons.get(item.id, item.recommendation_reason),
                    homepage_url=item.homepage_url,
                    supports_search_url=item.supports_search_url,
                    interaction_mode=item.interaction_mode,
                    requires_login=item.requires_login,
                    copyright_status=item.copyright_status,
                    copyright_notice=item.copyright_notice,
                    config_version=item.version,
                )
                for index, item in enumerate(selected_platforms[:5], start=1)
            ],
            generation_status=GenerationStatus(**generation_status.model_dump()),
            is_ai_generated=generation_status.ai_used,
            core_intent_category=core_intent_category,
            uncertainties=uncertainties,
        )
