import json

import pytest
from pydantic import ValidationError

from app.data.keyword_knowledge import (
    KEYWORD_CONCEPTS,
    KEYWORD_KNOWLEDGE_BASE,
    ConceptRelation,
    KeywordConcept,
    KeywordKnowledgeBase,
    build_knowledge_base,
)
from app.models.schemas import (
    KnowledgeExpansionCandidate,
    KnowledgeExpansionResult,
    MockKeywordOutput,
    SmartOptimizationOutput,
)
from app.providers import (
    InMemoryUsageQuota,
    LanguageModelError,
    MockEmbeddingProvider,
    MockLanguageModelProvider,
    parse_structured_model_response,
)
from app.services import ContextBuilder, KeywordOptimizeService, KeywordRetriever


def concept(**overrides) -> KeywordConcept:
    data = {
        "id": "subject_test",
        "canonical": {"zh": "测试主体", "en": "test subject"},
        "aliases": {"zh": ["测试别名"], "en": ["test alias"]},
        "category": "subject",
        "search_terms": {"zh": ["测试主体"], "en": ["test subject"]},
        "related_concepts": [],
        "applicable_personas": [],
        "applicable_platforms": [],
        "embedding_text": "测试主体 test subject 测试别名 test alias",
        "enabled": True,
        "version": 1,
    }
    data.update(overrides)
    return KeywordConcept.model_validate(data)


def test_chinese_and_english_aliases_match_one_concept():
    retriever = KeywordRetriever(use_local_knowledge=True)
    zh = retriever.retrieve("可爱的猫咪")
    en = retriever.retrieve("cute kitty")
    duplicate = retriever.retrieve("猫 cat kitty")
    assert zh["keywords"][0]["source_id"] == "subject_cat"
    assert en["keywords"][0]["source_id"] == "subject_cat"
    assert [item["source_id"] for item in duplicate["keywords"]].count("subject_cat") == 1


def test_all_major_categories_have_multiple_valid_examples():
    counts = {}
    for item in KEYWORD_KNOWLEDGE_BASE.concepts:
        counts[item.category] = counts.get(item.category, 0) + 1
        assert item.embedding_text.strip()
    assert all(
        counts[category] >= 2
        for category in (
            "subject",
            "scene",
            "color",
            "style",
            "composition",
            "quality_modifier",
            "general",
        )
    )


def test_exact_duplicate_concepts_are_collapsed():
    knowledge_base = build_knowledge_base([KEYWORD_CONCEPTS[0], KEYWORD_CONCEPTS[0]])
    assert len(knowledge_base.concepts) == 1


def test_disabled_concept_does_not_participate_in_retrieval():
    result = KeywordRetriever(use_local_knowledge=True).retrieve("停用示例 disabled example")
    assert result["keywords"] == []


def test_invalid_relation_shape_and_missing_target_are_rejected():
    with pytest.raises(ValidationError):
        ConceptRelation(concept_id="valid_id", relation="uncontrolled", weight=0.5)
    invalid = concept(
        related_concepts=[{"concept_id": "missing_target", "relation": "associated", "weight": 0.5}]
    )
    with pytest.raises(ValidationError, match="missing concept"):
        KeywordKnowledgeBase(concepts=(invalid,))


def test_blank_embedding_text_is_rejected():
    with pytest.raises(ValidationError, match="embedding_text"):
        concept(embedding_text="   ")


def test_relation_expansion_never_adds_an_unmatched_subject():
    cat = concept(
        id="subject_cat_local",
        canonical={"zh": "猫", "en": "cat"},
        related_concepts=[
            {"concept_id": "subject_dog_local", "relation": "associated", "weight": 1}
        ],
    )
    dog = concept(
        id="subject_dog_local",
        canonical={"zh": "狗", "en": "dog"},
        aliases={"zh": [], "en": []},
        search_terms={"zh": ["狗"], "en": ["dog"]},
        embedding_text="狗 dog",
    )
    result = KeywordRetriever(
        knowledge_base=KeywordKnowledgeBase(concepts=(cat, dog)),
        use_local_knowledge=True,
    ).retrieve("猫")
    assert [item["text"] for item in result["keywords"]] == ["cat"]


def test_knowledge_base_and_controlled_relation_retrieval():
    result = KeywordRetriever(use_local_knowledge=True).retrieve(
        "暖色咖啡店海报", "graphic_designer", ["unsplash"]
    )
    assert "coffee shop" in [item["text"] for item in result["keywords"]]
    assert result["persona_rules"] and result["platform_rules"]
    assert {"score", "source_type", "reason"} <= result["keywords"][0].keys()


def test_mocks_are_deterministic_and_structured():
    provider = MockEmbeddingProvider()
    assert provider.embed(["coffee"]) == provider.embed(["coffee"])
    prompt = ContextBuilder().build(
        "暖色咖啡店", None, {"keywords": []}, allowed_platforms=[]
    )
    output = MockKeywordOutput.model_validate(MockLanguageModelProvider().generate_keywords(prompt))
    assert output.expanded_terms[0].keyword == "warm lighting"


def test_optional_platforms_and_persona_are_applied():
    response = KeywordOptimizeService().optimize("咖啡店海报", "graphic_designer", ["pexels"])
    assert response.original_query == "咖啡店海报"
    assert [item.platform for item in response.platforms] == ["pexels"]


def test_embedding_and_llm_failures_degrade():
    class BrokenEmbedding:
        def embed(self, texts):
            raise RuntimeError("offline")

    class BrokenLLM:
        def generate_keywords(self, prompt):
            return {"invalid": True}

    result = KeywordRetriever(BrokenEmbedding(), use_local_knowledge=True).retrieve("咖啡店")
    assert result["keywords"]
    response = KeywordOptimizeService(
        retriever=KeywordRetriever(BrokenEmbedding(), use_local_knowledge=True),
        llm_provider=BrokenLLM(),
    ).optimize("咖啡店")
    assert response.original_query == "咖啡店"
    assert response.degraded


def test_empty_input_does_not_call_providers():
    class ExplodingProvider:
        def suggest(self, query):
            pytest.fail("provider must not be called")

    assert KeywordOptimizeService(ExplodingProvider()).optimize(" ").suggestions == []


def test_basic_never_calls_language_model_and_smart_does():
    class CountingLLM:
        calls = 0

        def generate_keywords(self, prompt):
            self.calls += 1
            return MockLanguageModelProvider().generate_keywords(prompt)

    provider = CountingLLM()
    service = KeywordOptimizeService(llm_provider=provider)
    basic = service.optimize("暖色咖啡店", optimization_mode="basic")
    smart = service.optimize("暖色咖啡店", optimization_mode="smart")
    assert basic.generation_status.status == "not_requested"
    assert smart.generation_status.status == "generated"
    assert not basic.generation_status.ai_used
    assert smart.generation_status.ai_used
    assert provider.calls == 1
    assert smart.suggestions[0].keyword == "暖色咖啡店"
    assert "warm lighting" in [item.keyword for item in smart.expanded_terms]
    assert next(
        item for item in smart.expanded_terms if item.keyword == "warm lighting"
    ).derived_from == ["暖色咖啡店"]


def test_prompt_contains_only_approved_context_and_limits():
    prompt = ContextBuilder().build(
        "脱敏描述",
        "graphic_designer",
        {"keywords": [{"text": "poster", "category": "style", "reason": "候选"}]},
        language="zh",
        allowed_platforms=[{"id": "huaban", "reason": "设计参考"}],
    )
    payload = json.loads(prompt)
    assert set(payload) == {
        "original_description", "language", "persona_context", "knowledge_candidates",
        "allowed_platforms", "limits", "instructions",
    }
    assert payload["limits"] == {"core_terms": 6, "expanded_terms": 8, "platform_plans": 5}
    assert "url" not in prompt.casefold() or payload["instructions"]["do_not_return_urls"]


def smart_output(**overrides):
    payload = {
        "core_intent_category": "general",
        "core_terms": [],
        "expanded_terms": [],
        "uncertainties": [],
        "platform_plans": [],
    }
    payload.update(overrides)
    return SmartOptimizationOutput.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        json.dumps({"core_intent_category": "general", "core_terms": [{}]}),
        json.dumps(
            {
                "core_intent_category": "general",
                "core_terms": [],
                "expanded_terms": [],
                "uncertainties": [],
                "platform_plans": [],
                "url": "https://sensitive.invalid",
            }
        ),
    ],
)
def test_provider_boundary_rejects_invalid_json_and_extra_fields(payload):
    with pytest.raises(LanguageModelError):
        parse_structured_model_response(payload)


def test_structured_limits_are_strict():
    term = {"keyword": "term", "category": "general", "derived_from": ["input"], "reason": "test"}
    with pytest.raises(ValidationError):
        SmartOptimizationOutput.model_validate({
                "core_intent_category": "general",
                "core_terms": [{**term, "keyword": f"t{i}"} for i in range(7)],
                "expanded_terms": [],
                "uncertainties": [],
                "platform_plans": [],
            }
        )


@pytest.mark.parametrize("failure", ["unknown_platform", "invented_subject", "timeout"])
def test_smart_validation_failures_fall_back_to_basic(failure):
    class InvalidLLM:
        def generate_keywords(self, prompt):
            if failure == "timeout":
                raise TimeoutError
            if failure == "unknown_platform":
                return smart_output(
                    platform_plans=[{"platform_id": "evil", "priority": 1, "reason": "x"}]
                )
            return smart_output(
                expanded_terms=[
                    {
                        "keyword": "dragon",
                        "category": "subject",
                        "derived_from": ["猫海报"],
                        "reason": "unsupported",
                    }
                ]
            )

    response = KeywordOptimizeService(llm_provider=InvalidLLM()).optimize(
        "猫海报", "graphic_designer", optimization_mode="smart"
    )
    assert response.generation_status.status == "fallback"
    assert not response.generation_status.ai_used
    assert response.suggestions[0].keyword == "猫海报"
    assert all(item.keyword != "dragon" for item in response.suggestions)


def test_quota_and_model_platform_priority_are_enforced():
    class OrderedLLM:
        def generate_keywords(self, prompt):
            return smart_output(platform_plans=[
                {"platform_id": "pinterest", "priority": 1, "reason": "首选情绪板"},
                {"platform_id": "huaban", "priority": 2, "reason": "中文案例"},
            ])

    quota = InMemoryUsageQuota(1)
    service = KeywordOptimizeService(llm_provider=OrderedLLM(), quota=quota)
    generated = service.optimize("猫海报", "graphic_designer", optimization_mode="smart")
    exhausted = service.optimize("猫海报", "graphic_designer", optimization_mode="smart")
    assert [item.platform for item in generated.platform_recommendations] == ["pinterest", "huaban"]
    assert generated.platform_recommendations[0].reason == "首选情绪板"
    assert generated.generation_status.remaining_uses == 0
    assert exhausted.generation_status.status == "fallback"
    assert exhausted.generation_status.remaining_uses == 0


class StubExternalOrchestrator:
    def __init__(self, results):
        self.results = results

    def expand(self, value):
        return self.results, []


def external_result(provider, term, *, status="live"):
    relation = "alias" if provider == "wikidata" else "IsA"
    return KnowledgeExpansionResult(
        provider=provider,
        status="success",
        version="test-v1",
        source_status=status,
        candidates=[
            KnowledgeExpansionCandidate(
                term=term,
                language="en",
                relation=relation,
                source=provider,
                source_id=f"{provider}:{term}",
                reason="外部知识候选",
                confidence=0.8,
                derived_from=["query-key"],
            )
        ],
    )


def test_default_retrieval_does_not_match_finite_local_concepts():
    result = KeywordRetriever().retrieve("猫 咖啡店 城市", "graphic_designer")
    assert all(item["text"] not in {"cat", "coffee shop", "city"} for item in result["keywords"])
    assert "copy space" not in [item["text"] for item in result["keywords"]]
    assert result["platform_rules"]


def test_unseen_external_terms_are_primary_and_never_marked_rules_only():
    retriever = KeywordRetriever(
        external_orchestrator=StubExternalOrchestrator(
            [
                external_result("wikidata", "bioluminescent architecture"),
                external_result("conceptnet", "speculative habitat"),
            ]
        )
    )
    response = KeywordOptimizeService(retriever=retriever).optimize("未知发光建筑")
    assert response.suggestions[0].source == "original"
    assert [item.keyword for item in response.suggestions[1:]] == [
        "bioluminescent architecture",
        "speculative habitat",
    ]
    assert all(item.source == "external" for item in response.suggestions[1:])
    assert response.retrieval.strategy == "external"
    assert response.query.startswith("未知发光建筑")


def test_external_candidates_are_casefold_deduplicated():
    retriever = KeywordRetriever(
        external_orchestrator=StubExternalOrchestrator(
            [
                external_result("wikidata", "Novel Form"),
                external_result("conceptnet", "novel form"),
            ]
        )
    )
    response = KeywordOptimizeService(retriever=retriever).optimize("new concept")
    assert [item.keyword.casefold() for item in response.suggestions].count("novel form") == 1


@pytest.mark.parametrize(
    ("query", "normalized"),
    [
        ("  未见   中文词  ", "未见 中文词"),
        ("  unseen   english term  ", "unseen english term"),
        ("  mixed   未见词  example ", "mixed 未见词 example"),
    ],
)
def test_all_external_failures_keep_normalized_query_and_platform_urls(query, normalized):
    response = KeywordOptimizeService().optimize(query)
    assert response.original_query == normalized
    assert response.query == normalized
    assert [item.keyword for item in response.suggestions] == [normalized]
    assert response.retrieval.strategy == "fallback"
    assert response.platforms and all(item.query and item.url for item in response.platforms)
    assert {item.status for item in response.knowledge_sources} == {"original_fallback"}
