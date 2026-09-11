import pytest

from app.data.persona_rules import PERSONAS
from app.services.rag import KeywordRetriever, PersonaRuleEngine


@pytest.mark.parametrize(
    ("persona", "query", "expected_modifier"),
    [
        ("graphic_designer", "猫品牌营销海报", "copy space"),
        ("illustrator", "猫角色概念配色", "character design"),
        ("photographer", "猫摄影光线镜头景别", "natural light"),
        ("ecommerce_worker", "猫商品白底商业广告", "product showcase"),
        ("ui_designer", "猫 UI 界面手机组件", "user interface"),
    ],
)
def test_five_personas_apply_conditional_modifiers(persona, query, expected_modifier):
    result = KeywordRetriever().retrieve(query, persona)
    keywords = result["keywords"]
    assert expected_modifier in [item["text"] for item in keywords]
    assert all(item["reason"] for item in keywords)
    assert result["persona_rules"][0]["source_id"] == persona


def test_profiles_are_complete_and_have_stable_ids():
    assert set(PERSONAS) == {
        "graphic_designer",
        "illustrator",
        "photographer",
        "ecommerce_worker",
        "ui_designer",
    }
    for persona_id, profile in PERSONAS.items():
        assert profile.id == persona_id
        assert profile.name.zh and profile.name.en
        assert profile.goal and profile.category_weights and profile.preferred_modifiers
        assert profile.blocked_expansions and profile.platform_priority
        assert profile.prompt_context and profile.version == 1


def test_no_persona_adds_no_persona_specific_terms():
    result = KeywordRetriever().retrieve("猫品牌营销海报")
    assert result["persona_rules"] == []
    assert all(item["source_type"] != "persona_modifier" for item in result["keywords"])


def test_ui_modifiers_require_ui_intent():
    without_ui = KeywordRetriever().retrieve(
        "猫手机设备组件", "ui_designer"
    )
    assert all(item["source_type"] != "persona_modifier" for item in without_ui["keywords"])
    with_ui = KeywordRetriever().retrieve(
        "猫 UI 手机组件", "ui_designer"
    )
    assert {"user interface", "device mockup", "design system"} <= {
        item["text"] for item in with_ui["keywords"]
    }


def test_blocked_expansions_do_not_remove_direct_subjects():
    candidates = [
        {
            "text": "cat",
            "category": "subject",
            "source_type": "keyword",
            "source_id": "subject_cat",
            "score": 0.82,
            "reason": "直接匹配",
        },
        {
            "text": "people",
            "category": "subject",
            "source_type": "concept_relation",
            "source_id": "subject_person",
            "score": 0.7,
            "reason": "关系扩展",
        },
    ]
    ranked, _ = PersonaRuleEngine().apply("猫海报", candidates, "graphic_designer")
    assert [item["text"] for item in ranked if item["category"] == "subject"] == ["cat"]


def test_persona_ranking_is_stable_and_explains_weights():
    candidates = [
        {
            "text": "城市", "category": "scene", "source_type": "keyword",
            "source_id": "city", "score": 0.8, "reason": "直接匹配", "group": "core",
        },
        {
            "text": "海报", "category": "composition", "source_type": "keyword",
            "source_id": "poster", "score": 0.8, "reason": "直接匹配", "group": "core",
        },
    ]
    first, _ = PersonaRuleEngine().apply("猫城市海报", candidates, "graphic_designer")
    second, _ = PersonaRuleEngine().apply("猫城市海报", candidates, "graphic_designer")
    assert first == second
    assert first[0]["category"] == "composition"
    weighted = [item for item in first if item["source_type"] != "persona_modifier"]
    assert all("分类权重" in item["reason"] for item in weighted)


def test_retriever_keeps_persona_rules_without_handwritten_subject_lookup():
    result = KeywordRetriever().retrieve("猫品牌营销海报", "graphic_designer")
    assert all(item["text"] != "cat" for item in result["keywords"])
    assert "copy space" in [item["text"] for item in result["keywords"]]
    assert result["persona_rules"] and result["platform_rules"]


def test_persona_platform_priority_comes_from_shared_configuration():
    assert PERSONAS["photographer"].platform_priority == [
        "unsplash", "pexels", "vcg", "pixabay", "pinterest", "xiaohongshu"
    ]
    assert PERSONAS["ecommerce_worker"].platform_priority == [
        "chuangkit", "freepik", "vcg", "pexels", "xiaohongshu", "huaban", "pinterest"
    ]
