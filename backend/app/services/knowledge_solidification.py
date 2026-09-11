from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from app.data.keyword_knowledge import KeywordConcept

SAFE_RELATIONS = {"exact", "alias", "translation", "HasType", "UsedFor", "AtLocation"}
STABLE_SOURCES = {"wikidata", "conceptnet"}


class CandidateMetric(BaseModel):
    term: str = Field(min_length=1, max_length=120)
    canonical_zh: str = Field(min_length=1, max_length=120)
    canonical_en: str = Field(min_length=1, max_length=120)
    aliases_zh: list[str] = Field(default_factory=list)
    aliases_en: list[str] = Field(default_factory=list)
    category: str
    source: str
    relation: str
    uses: int = Field(ge=0)
    kept: int = Field(ge=0)
    removed: int = Field(ge=0)
    applicable_platforms: list[str] = Field(default_factory=list)
    reviewed: bool = False
    enabled: bool = True

    @field_validator("category")
    @classmethod
    def valid_category(cls, value: str) -> str:
        allowed = {
            "subject",
            "scene",
            "color",
            "style",
            "composition",
            "quality_modifier",
            "general",
        }
        if value not in allowed:
            raise ValueError("unsupported keyword category")
        return value


class SolidificationReport(BaseModel):
    version: int
    accepted: list[KeywordConcept] = Field(default_factory=list)
    rejected: list[dict[str, str]] = Field(default_factory=list)
    dry_run: bool = True


def stable_concept_id(metric: CandidateMetric) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", metric.canonical_en.casefold()).strip("_") or "term"
    digest = sha256(f"{metric.canonical_zh}|{metric.canonical_en}".encode()).hexdigest()[:8]
    return f"external_{base[:40]}_{digest}"


class KnowledgeSolidifier:
    def __init__(self, min_uses: int = 5, min_keep_rate: float = 0.6, max_remove_rate: float = 0.3):
        self.min_uses = min_uses
        self.min_keep_rate = min_keep_rate
        self.max_remove_rate = max_remove_rate

    def evaluate(self, metrics: list[CandidateMetric], version: int) -> SolidificationReport:
        accepted: dict[str, KeywordConcept] = {}
        rejected = []
        for metric in metrics:
            reason = self._rejection_reason(metric)
            concept_id = stable_concept_id(metric)
            if reason:
                rejected.append({"id": concept_id, "reason": reason})
                continue
            concept = KeywordConcept(
                id=concept_id,
                canonical={"zh": metric.canonical_zh, "en": metric.canonical_en},
                aliases={"zh": metric.aliases_zh, "en": metric.aliases_en},
                category=metric.category,
                search_terms={
                    "zh": [metric.canonical_zh, *metric.aliases_zh],
                    "en": [metric.canonical_en, *metric.aliases_en],
                },
                applicable_platforms=metric.applicable_platforms,
                embedding_text=f"{metric.canonical_zh} {metric.canonical_en}",
                enabled=metric.enabled,
                version=version,
            )
            accepted[concept_id] = concept
        return SolidificationReport(
            version=version, accepted=list(accepted.values()), rejected=rejected
        )

    def _rejection_reason(self, metric: CandidateMetric) -> str | None:
        if not metric.reviewed:
            return "未完成人工审核"
        if metric.source not in STABLE_SOURCES or metric.relation not in SAFE_RELATIONS:
            return "来源或关系不在安全白名单"
        if metric.uses < self.min_uses:
            return "使用次数不足"
        if metric.kept / max(metric.uses, 1) < self.min_keep_rate:
            return "用户保留率不足"
        if metric.removed / max(metric.uses, 1) > self.max_remove_rate:
            return "用户删除率过高"
        if not metric.canonical_zh.strip() or not metric.canonical_en.strip():
            return "多语言标签不完整"
        return None

    @staticmethod
    def write_reviewed(
        report: SolidificationReport, output: str | Path, *, approve: bool = False
    ) -> bool:
        if not approve:
            return False
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": report.version,
            "concepts": [item.model_dump(mode="json") for item in report.accepted],
        }
        serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        if path.exists() and path.read_text(encoding="utf-8") == serialized:
            return False
        path.write_text(serialized, encoding="utf-8")
        return True
