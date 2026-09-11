from __future__ import annotations

import re
import threading
from hashlib import sha256
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np

from app.infrastructure.cache import Cache
from app.models.schemas import (
    KnowledgeExpansionCandidate,
    KnowledgeExpansionRequest,
    KnowledgeExpansionResult,
)


@runtime_checkable
class KnowledgeExpansionProvider(Protocol):
    name: str
    version: str
    enabled: bool

    def expand(self, request: KnowledgeExpansionRequest) -> KnowledgeExpansionResult: ...


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
        cache: Cache[KnowledgeExpansionResult] | None = None,
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
        self.cache = cache
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
        cache_key = sha256(
            f"{request.language}:{request.query.casefold()}".encode()
        ).hexdigest()
        cached = self.cache.get(cache_key) if self.cache else None
        if cached is not None:
            return cached.model_copy(deep=True, update={"source_status": "fresh_cache"})
        result = self._expand_uncached(request)
        if self.cache:
            self.cache.set(cache_key, result.model_copy(deep=True))
        return result

    def _expand_uncached(self, request: KnowledgeExpansionRequest) -> KnowledgeExpansionResult:
        self._load()
        assert self._indices is not None and self._vectors is not None and self._words is not None
        seeds = self._query_terms(request.query)
        if not seeds:
            return KnowledgeExpansionResult(
                provider=self.name,
                status="empty",
                version=self.version,
                warning="本地词向量未收录可用中文词组",
                source_status="live",
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
                    reason=f"与“{'、'.join(seeds)}”语义相近",
                    confidence=round(similarity, 4),
                    category="general",
                    derived_from=seeds,
                    license="Tencent AI Lab Embedding Corpus",
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
