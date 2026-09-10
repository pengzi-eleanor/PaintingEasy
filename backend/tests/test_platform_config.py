from urllib.parse import unquote

from app.services.platforms import PLATFORMS, build_platform_query, build_platform_url


def test_shared_configuration_contains_six_platforms_and_required_fields():
    assert [item.id for item in PLATFORMS] == ["unsplash", "pexels", "pixabay", "freepik", "vcg", "huaban"]
    for item in PLATFORMS:
        assert item.name and item.strengths and item.weaknesses and item.term_rules and item.version
        assert item.query_policy.max_terms > 0 and item.url_template.count("{query}") == 1
        assert all(rule.reason for rule in item.term_rules)


def test_platform_query_preserves_core_terms_applies_limit_and_encodes_url():
    config = PLATFORMS[0]
    query = build_platform_query(config, ["red chair"], ["studio", "extra", "more", "last", "overflow", "x", "y"], "en")
    assert "red chair" in query
    assert query.split(config.query_policy.separator)[0:2] == ["red", "chair"]
    assert query.count(config.query_policy.separator) < config.query_policy.max_terms + 2
    assert "%20" in build_platform_url(config, query)
    assert unquote(build_platform_url(config, query)).endswith(query)


def test_disabled_platform_is_not_selected_and_login_is_explicit():
    assert {item.id for item in PLATFORMS if item.enabled} == {item.id for item in PLATFORMS}
    assert next(item for item in PLATFORMS if item.id == "vcg").requires_login
    assert next(item for item in PLATFORMS if item.id == "huaban").requires_login
