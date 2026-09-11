import json

from app.data.keyword_knowledge import build_knowledge_base
from app.services.knowledge_solidification import CandidateMetric, KnowledgeSolidifier


def metric(**updates):
    data = {
        "term": "cafe",
        "canonical_zh": "咖啡馆",
        "canonical_en": "cafe",
        "aliases_zh": ["咖啡店"],
        "aliases_en": ["coffee shop"],
        "category": "scene",
        "source": "wikidata",
        "relation": "alias",
        "uses": 10,
        "kept": 8,
        "removed": 1,
        "applicable_platforms": ["pexels"],
        "reviewed": True,
    }
    data.update(updates)
    return CandidateMetric.model_validate(data)


def test_filter_deduplicate_version_and_load(tmp_path):
    report = KnowledgeSolidifier().evaluate([metric(), metric()], version=2)
    assert len(report.accepted) == 1
    assert report.accepted[0].version == 2 and report.accepted[0].id.startswith("external_cafe_")
    build_knowledge_base(report.accepted)
    output = tmp_path / "promoted.json"
    assert not KnowledgeSolidifier.write_reviewed(report, output)
    assert not output.exists()
    assert KnowledgeSolidifier.write_reviewed(report, output, approve=True)
    assert not KnowledgeSolidifier.write_reviewed(report, output, approve=True)
    assert json.loads(output.read_text(encoding="utf-8"))["version"] == 2


def test_rejects_unreviewed_unsafe_low_quality_and_supports_disabled_rollback():
    metrics = [
        metric(reviewed=False),
        metric(relation="RelatedTo"),
        metric(uses=2, kept=2),
        metric(kept=2),
        metric(removed=8),
        metric(enabled=False),
    ]
    report = KnowledgeSolidifier().evaluate(metrics, version=3)
    assert len(report.accepted) == 1 and not report.accepted[0].enabled
    assert len(report.rejected) == 5
