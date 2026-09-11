from urllib.parse import unquote

from app.services.platforms import (
    PLATFORM_CATALOG,
    PLATFORMS,
    build_platform_query,
    build_platform_url,
    platforms_for_persona,
)


def test_shared_configuration_contains_required_platforms_and_fields():
    assert PLATFORM_CATALOG.config_version == "persona-platforms-v1"
    assert PLATFORM_CATALOG.review_status == "pending_user_review"
    assert {item.id for item in PLATFORMS} == {
        "huaban", "xiaohongshu", "pinterest", "pixso", "chuangkit", "behance",
        "freepik", "pixiv", "artstation", "unsplash", "pexels", "vcg", "pixabay",
        "figma_community", "dribbble",
    }
    for item in PLATFORMS:
        assert item.name and item.strengths and item.weaknesses and item.version
        assert item.supported_languages and item.recommendation_reason and item.copyright_notice
        assert item.query_policy.max_terms > 0
        assert bool(item.url_template) is item.supports_search_url
        assert all(rule.reason for rule in item.term_rules)


def test_platform_query_preserves_core_terms_applies_limit_and_encodes_url():
    config = PLATFORMS[0]
    query = build_platform_query(
        config,
        ["red chair"],
        ["studio", "extra", "more", "last", "overflow", "x", "y"],
        "en",
    )
    assert "red chair" in query
    assert query.split(config.query_policy.separator)[0:2] == ["red", "chair"]
    assert query.count(config.query_policy.separator) < config.query_policy.max_terms + 2
    url = build_platform_url(config, query)
    assert url is not None and "%20" in url
    assert unquote(url).endswith(query)


def test_disabled_platform_is_not_selected_and_login_is_explicit():
    assert {item.id for item in PLATFORMS if item.enabled} == {item.id for item in PLATFORMS}
    assert next(item for item in PLATFORMS if item.id == "vcg").requires_login
    assert next(item for item in PLATFORMS if item.id == "huaban").requires_login


def test_persona_order_is_stable_and_matches_review_draft():
    assert [item.id for item in platforms_for_persona("graphic_designer")] == [
        "huaban", "xiaohongshu", "pinterest", "pixso", "chuangkit", "behance", "freepik"
    ]
    assert [item.id for item in platforms_for_persona("ui_designer")] == [
        "figma_community", "pixso", "dribbble", "behance", "pinterest", "huaban", "freepik"
    ]


def test_unstable_search_urls_are_not_fabricated_and_copyright_is_explicit():
    xiaohongshu = next(item for item in PLATFORMS if item.id == "xiaohongshu")
    assert build_platform_url(xiaohongshu, "猫 海报") is None
    assert xiaohongshu.interaction_mode == "in_site_search"
    inspiration = [item for item in PLATFORMS if item.copyright_status == "inspiration_only"]
    assert inspiration and all("不能默认下载商用" in item.copyright_notice for item in inspiration)
    variable = [item for item in PLATFORMS if item.copyright_status == "license_per_item"]
    assert variable and all("逐项核对" in item.copyright_notice for item in variable)
