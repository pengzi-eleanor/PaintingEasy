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
from app.models.schemas import MockKeywordOutput
from app.providers import MockEmbeddingProvider, MockLanguageModelProvider
from app.services import KeywordOptimizeService, KeywordRetriever


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
    retriever = KeywordRetriever()
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
    result = KeywordRetriever().retrieve("停用示例 disabled example")
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
    result = KeywordRetriever(knowledge_base=KeywordKnowledgeBase(concepts=(cat, dog))).retrieve(
        "猫"
    )
    assert [item["text"] for item in result["keywords"]] == ["cat"]


def test_knowledge_base_and_controlled_relation_retrieval():
    result = KeywordRetriever().retrieve("暖色咖啡店海报", "graphic_designer", ["unsplash"])
    assert "coffee shop" in [item["text"] for item in result["keywords"]]
    assert result["persona_rules"] and result["platform_rules"]
    assert {"score", "source_type", "reason"} <= result["keywords"][0].keys()


def test_mocks_are_deterministic_and_structured():
    provider = MockEmbeddingProvider()
    assert provider.embed(["coffee"]) == provider.embed(["coffee"])
    output = MockKeywordOutput.model_validate(
        MockLanguageModelProvider().generate_keywords("原始描述：暖色咖啡店")
    )
    assert output.derived_terms[0].keyword == "warm lighting"


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

    result = KeywordRetriever(BrokenEmbedding()).retrieve("咖啡店")
    assert result["keywords"]
    response = KeywordOptimizeService(
        retriever=KeywordRetriever(BrokenEmbedding()), llm_provider=BrokenLLM()
    ).optimize("咖啡店")
    assert response.original_query == "咖啡店"
    assert response.degraded


def test_empty_input_does_not_call_providers():
    class ExplodingProvider:
        def suggest(self, query):
            pytest.fail("provider must not be called")

    assert KeywordOptimizeService(ExplodingProvider()).optimize(" ").suggestions == []
