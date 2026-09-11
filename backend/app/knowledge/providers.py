from __future__ import annotations

import re
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol, runtime_checkable
from urllib.parse import quote

import httpx
import numpy as np

from app.data.keyword_knowledge import KEYWORD_KNOWLEDGE_BASE
from app.models.schemas import (
    KnowledgeExpansionCandidate,
    KnowledgeExpansionRequest,
    KnowledgeExpansionResult,
)

from .cache import KnowledgeCache, NullKnowledgeCache


@runtime_checkable
class KnowledgeExpansionProvider(Protocol):
    name: str
    version: str
    enabled: bool

    def expand(self, request: KnowledgeExpansionRequest) -> KnowledgeExpansionResult: ...


def _language(value: str) -> str:
    zh = bool(re.search(r"[\u4e00-\u9fff]", value))
    en = bool(re.search(r"[A-Za-z]", value))
    return "mixed" if zh and en else "zh" if zh else "en" if en else "auto"


class LocalKnowledgeExpansionProvider:
    name = "local_rule"
    version = "keyword-knowledge-v1"
    enabled = True

    def __init__(self, knowledge_base=None):
        self.knowledge_base = knowledge_base or KEYWORD_KNOWLEDGE_BASE

    def expand(self, request: KnowledgeExpansionRequest) -> KnowledgeExpansionResult:
        if not request.query:
            return KnowledgeExpansionResult(
                provider=self.name, status="empty", version=self.version
            )
        query = request.query.casefold()
        direct = []
        candidates = []
        seen: set[str] = set()
        for concept in self.knowledge_base.concepts:
            if not concept.enabled or concept.id in seen:
                continue
            matched = next(
                (term for term in concept.match_terms() if term.casefold() in query), None
            )
            if matched is None:
                continue
            seen.add(concept.id)
            direct.append(concept)
            candidates.append(
                KnowledgeExpansionCandidate(
                    term=concept.canonical.en,
                    language="en",
                    aliases=[*concept.aliases.zh, *concept.aliases.en],
                    relation="exact",
                    source=self.name,
                    source_id=concept.id,
                    reason=f"与用户描述中的{matched}相关",
                    confidence=0.82,
                    category=concept.category,
                    derived_from=[matched],
                    applicable_platforms=concept.applicable_platforms,
                )
            )
        by_id = self.knowledge_base.by_id
        for source in direct:
            for relation in source.related_concepts:
                target = by_id[relation.concept_id]
                if not target.enabled or target.id in seen or target.category == "subject":
                    continue
                seen.add(target.id)
                candidates.append(
                    KnowledgeExpansionCandidate(
                        term=target.canonical.en,
                        language="en",
                        aliases=[*target.aliases.zh, *target.aliases.en],
                        relation="RelatedTo",
                        source=self.name,
                        source_id=target.id,
                        reason=f"由{source.canonical.zh}的{relation.relation}关系扩展",
                        confidence=round(0.82 * relation.weight, 4),
                        category=target.category,
                        derived_from=[source.id],
                        applicable_platforms=target.applicable_platforms,
                    )
                )
        return KnowledgeExpansionResult(
            provider=self.name,
            status="success" if candidates else "empty",
            candidates=candidates,
            version=self.version,
        )


class TencentWord2VecKnowledgeProvider:
    """Local Chinese related-word lookup backed by Tencent's light Word2Vec corpus."""

    name = "tencent_word2vec"
    version = "tencent-ailab-light-143613-d200-v1"

    def __init__(
        self,
        model_path: str | Path,
        *,
        enabled: bool = True,
        topn: int = 6,
        min_similarity: float = 0.55,
    ):
        configured_path = Path(model_path)
        backend_relative = Path(__file__).resolve().parents[2] / configured_path
        self.model_path = (
            configured_path
            if configured_path.is_absolute() or configured_path.exists()
            else backend_relative
        )
        self.enabled = enabled
        self.topn = topn
        self.min_similarity = min_similarity
        self._words: list[str] | None = None
        self._indices: dict[str, int] | None = None
        self._vectors: np.ndarray | None = None
        self._load_lock = threading.Lock()

    def _load(self) -> None:
        if self._vectors is not None:
            return
        with self._load_lock:
            if self._vectors is not None:
                return
            with self.model_path.open("rb") as stream:
                vocabulary_size, dimensions = map(int, stream.readline().split())
                words: list[str] = []
                vectors = np.empty((vocabulary_size, dimensions), dtype=np.float32)
                for row in range(vocabulary_size):
                    token = bytearray()
                    while True:
                        char = stream.read(1)
                        if not char:
                            raise ValueError("腾讯词向量文件提前结束")
                        if char == b" ":
                            break
                        if char != b"\n":
                            token.extend(char)
                    words.append(token.decode("utf-8"))
                    vector = np.frombuffer(stream.read(dimensions * 4), dtype="<f4")
                    if vector.size != dimensions:
                        raise ValueError("腾讯词向量维度不完整")
                    vectors[row] = vector
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            vectors /= np.maximum(norms, np.finfo(np.float32).eps)
            self._words = words
            self._indices = {word: index for index, word in enumerate(words)}
            self._vectors = vectors

    @staticmethod
    def _is_candidate(term: str) -> bool:
        return (
            2 <= len(term) <= 12
            and re.fullmatch(r"[\u3400-\u4dbf\u4e00-\u9fff]+", term) is not None
        )

    def _query_terms(self, query: str) -> list[str]:
        assert self._indices is not None
        chunks = re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]+", query)
        matches: list[str] = []
        for chunk in chunks:
            if chunk in self._indices:
                matches.append(chunk)
                continue
            for size in range(min(6, len(chunk)), 1, -1):
                for start in range(len(chunk) - size + 1):
                    term = chunk[start : start + size]
                    if term in self._indices and term not in matches:
                        matches.append(term)
                        if len(matches) == 4:
                            return matches
        return matches[:4]

    def expand(self, request: KnowledgeExpansionRequest) -> KnowledgeExpansionResult:
        if not self.enabled or not request.query or request.language == "en":
            return KnowledgeExpansionResult(
                provider=self.name, status="empty", version=self.version
            )
        self._load()
        assert self._indices is not None and self._vectors is not None and self._words is not None
        seeds = self._query_terms(request.query)
        if not seeds:
            return KnowledgeExpansionResult(
                provider=self.name,
                status="empty",
                version=self.version,
                warning="本地词向量未收录可用中文词组",
            )
        seed_vector = self._vectors[[self._indices[seed] for seed in seeds]].mean(axis=0)
        seed_vector /= max(float(np.linalg.norm(seed_vector)), np.finfo(np.float32).eps)
        scores = self._vectors @ seed_vector
        pool_size = min(len(scores), max(50, self.topn * 10))
        pool = np.argpartition(scores, -pool_size)[-pool_size:]
        ranked = sorted(pool, key=lambda index: (-float(scores[index]), self._words[index]))
        candidates = []
        query_terms = {request.query, *seeds}
        for index in ranked:
            term = self._words[index]
            similarity = float(scores[index])
            if similarity < self.min_similarity:
                break
            if term in query_terms or not self._is_candidate(term):
                continue
            candidates.append(
                KnowledgeExpansionCandidate(
                    term=term,
                    language="zh",
                    relation="RelatedTo",
                    source=self.name,
                    source_id=f"tencent-word2vec:{index}",
                    reason=f"腾讯本地词向量与“{'、'.join(seeds)}”语义相近",
                    confidence=round(similarity, 4),
                    category="general",
                    derived_from=seeds,
                    license="CC-BY-3.0 research corpus",
                )
            )
            if len(candidates) == self.topn:
                break
        return KnowledgeExpansionResult(
            provider=self.name,
            status="success" if candidates else "empty",
            candidates=candidates,
            version=self.version,
            source_status="live",
        )


class CachedHttpKnowledgeProvider:
    name: str
    version: str

    def __init__(
        self,
        *,
        enabled: bool = False,
        client: httpx.Client | None = None,
        cache: KnowledgeCache | None = None,
        ttl_seconds: int = 2_592_000,
        empty_ttl_seconds: int = 86_400,
        failure_ttl_seconds: int = 300,
        stale_ttl_seconds: int = 7_776_000,
        timeout_seconds: float = 2.5,
    ):
        self.enabled = enabled
        self.client = client or httpx.Client(timeout=timeout_seconds)
        self.cache = cache or NullKnowledgeCache()
        self.success_ttl_seconds = ttl_seconds
        self.empty_ttl_seconds = empty_ttl_seconds
        self.failure_ttl_seconds = failure_ttl_seconds
        self.stale_ttl_seconds = stale_ttl_seconds

    def get_fresh(self, request: KnowledgeExpansionRequest) -> KnowledgeExpansionResult | None:
        cached = self.cache.get_fresh(self.name, request.language, request.query, self.version)
        if cached is None:
            return None
        return cached.model_copy(
            update={
                "source_status": (
                    "fresh_cache"
                    if cached.status not in {"failed", "degraded"}
                    else "original_fallback"
                )
            }
        )

    def get_stale(self, request: KnowledgeExpansionRequest) -> KnowledgeExpansionResult | None:
        stale = self.cache.get_stale(self.name, request.language, request.query, self.version)
        if stale is None:
            return None
        return stale.model_copy(
            update={
                "source_status": "stale_cache",
                "degraded": True,
                "warning": "实时知识扩展不可用，已使用通过当前校验的旧缓存",
            }
        )

    def fetch_live(self, request: KnowledgeExpansionRequest) -> KnowledgeExpansionResult:
        result = self._fetch(request).model_copy(update={"source_status": "live"})
        now = datetime.now(UTC)
        ttl = self.success_ttl_seconds if result.status == "success" else self.empty_ttl_seconds
        expires = now + timedelta(seconds=ttl)
        stale_until = now + timedelta(seconds=max(ttl, self.stale_ttl_seconds))
        self.cache.put(self.name, request.language, request.query, result, expires, stale_until)
        return result

    def record_failure(self, request: KnowledgeExpansionRequest) -> None:
        failure = KnowledgeExpansionResult(
            provider=self.name,
            status="failed",
            version=self.version,
            degraded=True,
            warning="外部知识扩展暂不可用",
            source_status="original_fallback",
        )
        now = datetime.now(UTC)
        failure_expiry = now + timedelta(seconds=self.failure_ttl_seconds)
        self.cache.put(
            self.name,
            request.language,
            request.query,
            failure,
            failure_expiry,
            failure_expiry,
        )

    def expand(self, request: KnowledgeExpansionRequest) -> KnowledgeExpansionResult:
        if not self.enabled or not request.query:
            return KnowledgeExpansionResult(
                provider=self.name,
                status="empty",
                version=self.version,
                source_status="original_fallback",
            )
        cached = self.get_fresh(request)
        if cached is not None:
            return cached
        try:
            return self.fetch_live(request)
        except Exception:
            stale = self.get_stale(request)
            if stale is not None:
                return stale
            self.record_failure(request)
            raise

    def _fetch(self, request: KnowledgeExpansionRequest) -> KnowledgeExpansionResult:
        raise NotImplementedError


class WikidataKnowledgeProvider(CachedHttpKnowledgeProvider):
    name = "wikidata"
    version = "wikidata-v1"
    endpoint = "https://www.wikidata.org/w/api.php"

    def __init__(self, *, endpoint: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.endpoint = endpoint or self.endpoint

    def _fetch(self, request: KnowledgeExpansionRequest) -> KnowledgeExpansionResult:
        language = "zh" if request.language in {"zh", "mixed", "auto"} else "en"
        response = self.client.get(
            self.endpoint,
            params={
                "action": "wbsearchentities",
                "search": request.query,
                "language": language,
                "uselang": language,
                "type": "item",
                "limit": 5,
                "format": "json",
            },
        )
        response.raise_for_status()
        search_items = response.json().get("search", [])
        ids = [str(item.get("id", "")) for item in search_items if item.get("id")]
        entities = {}
        if ids:
            details = self.client.get(
                self.endpoint,
                params={
                    "action": "wbgetentities",
                    "ids": "|".join(ids),
                    "props": "labels|aliases",
                    "languages": "zh|en",
                    "format": "json",
                },
            )
            details.raise_for_status()
            entities = details.json().get("entities", {})
        candidates = []
        seen = set()
        for item in search_items:
            entity = entities.get(str(item.get("id", "")), {})
            labels = entity.get("labels", {})
            label = str(labels.get("en", {}).get("value") or item.get("label", "")).strip()
            aliases = [
                str(value).strip() for value in item.get("aliases", []) if str(value).strip()
            ]
            for locale in ("zh", "en"):
                localized_label = str(labels.get(locale, {}).get("value", "")).strip()
                if localized_label:
                    aliases.append(localized_label)
                aliases.extend(
                    str(alias.get("value", "")).strip()
                    for alias in entity.get("aliases", {}).get(locale, [])
                    if str(alias.get("value", "")).strip()
                )
            aliases = list(dict.fromkeys(value for value in aliases if value != label))
            key = label.casefold()
            if not label or key in seen:
                continue
            seen.add(key)
            candidates.append(
                KnowledgeExpansionCandidate(
                    term=label,
                    language=_language(label),
                    aliases=aliases,
                    relation="alias",
                    source=self.name,
                    source_id=str(item.get("id", "wikidata-item")),
                    reason="Wikidata 标签或别名匹配",
                    confidence=0.72,
                    category="general",
                    derived_from=["query-key"],
                    license="CC0-1.0",
                )
            )
        return KnowledgeExpansionResult(
            provider=self.name,
            status="success" if candidates else "empty",
            candidates=candidates,
            version=self.version,
        )


class ConceptNetKnowledgeProvider(CachedHttpKnowledgeProvider):
    name = "conceptnet"
    version = "conceptnet-5.7"
    endpoint = "https://api.conceptnet.io"
    relation_priority = {
        "HasType": 0,
        "IsA": 0,
        "UsedFor": 1,
        "AtLocation": 2,
        "RelatedTo": 3,
    }

    def __init__(self, *, max_candidates: int = 6, endpoint: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.max_candidates = max_candidates
        self.endpoint = endpoint or self.endpoint

    def _fetch(self, request: KnowledgeExpansionRequest) -> KnowledgeExpansionResult:
        language = "zh" if request.language in {"zh", "mixed", "auto"} else "en"
        uri = f"/c/{language}/{quote(request.query.casefold().replace(' ', '_'))}"
        response = self.client.get(f"{self.endpoint}{uri}", params={"limit": 30})
        response.raise_for_status()
        candidates = []
        seen = set()
        for edge in response.json().get("edges", []):
            relation = str(edge.get("rel", {}).get("label", ""))
            if relation not in self.relation_priority:
                continue
            start, end = edge.get("start", {}), edge.get("end", {})
            other = end if str(start.get("@id", "")).startswith(uri) else start
            term = str(other.get("label", "")).strip()
            other_language = str(other.get("language", language))
            key = term.casefold()
            if not term or key in seen or other_language not in {"zh", "en"}:
                continue
            seen.add(key)
            candidates.append(
                KnowledgeExpansionCandidate(
                    term=term,
                    language=_language(term),
                    relation=relation,
                    source=self.name,
                    source_id=str(edge.get("@id", f"conceptnet:{key}"))[:200],
                    reason=f"ConceptNet {relation} 安全关系扩展",
                    confidence=min(1, max(0, float(edge.get("weight", 1)) / 3)),
                    category="general",
                    derived_from=["query-key"],
                    license=str(edge.get("license", "")) or None,
                )
            )
        candidates.sort(
            key=lambda item: (
                self.relation_priority[item.relation],
                -item.confidence,
                item.term.casefold(),
                item.source_id,
            )
        )
        candidates = candidates[: self.max_candidates]
        return KnowledgeExpansionResult(
            provider=self.name,
            status="success" if candidates else "empty",
            candidates=candidates,
            version=self.version,
        )
