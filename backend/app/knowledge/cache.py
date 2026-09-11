from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from app.models.schemas import KnowledgeExpansionCandidate, KnowledgeExpansionResult

CACHE_SCHEMA_VERSION = 2
RELATION_RULES_VERSION = "knowledge-relations-v2"
ALLOWED_RELATIONS = {
    "wikidata": {"exact", "alias", "translation"},
    "conceptnet": {"HasType", "IsA", "UsedFor", "AtLocation", "RelatedTo"},
}


def normalized_query_key(query: str) -> str:
    normalized = " ".join(query.casefold().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _as_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


class KnowledgeCache(Protocol):
    def get_fresh(
        self,
        provider: str,
        language: str,
        query: str,
        version: str,
        now: datetime | None = None,
    ) -> KnowledgeExpansionResult | None: ...

    def get_stale(
        self,
        provider: str,
        language: str,
        query: str,
        version: str,
        now: datetime | None = None,
    ) -> KnowledgeExpansionResult | None: ...

    def put(
        self,
        provider: str,
        language: str,
        query: str,
        result: KnowledgeExpansionResult,
        expires_at: datetime,
        stale_until: datetime | None = None,
    ) -> bool: ...

    def cleanup(self, now: datetime | None = None) -> int: ...


class NullKnowledgeCache:
    def get_fresh(self, *args, **kwargs) -> None:
        return None

    def get_stale(self, *args, **kwargs) -> None:
        return None

    def get(self, *args, **kwargs) -> None:
        return None

    def put(self, *args, **kwargs) -> bool:
        return False

    def cleanup(self, now: datetime | None = None) -> int:
        return 0


class SQLiteKnowledgeCache:
    """Store query digests and validated candidates; SQLite failures are cache misses."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        self._lock = threading.RLock()
        self.available = True
        try:
            self._initialize()
        except (OSError, sqlite3.Error):
            self.available = False

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=2)
        connection.execute("PRAGMA busy_timeout = 2000")
        return connection

    def _initialize(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS knowledge_cache (
                provider TEXT NOT NULL, language TEXT NOT NULL, query_key TEXT NOT NULL,
                version TEXT NOT NULL, status TEXT NOT NULL, candidates_json TEXT NOT NULL,
                degraded INTEGER NOT NULL, warning TEXT, created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL, validated INTEGER NOT NULL DEFAULT 1,
                stale_until TEXT, last_accessed_at TEXT, schema_version INTEGER NOT NULL DEFAULT 2,
                rules_version TEXT NOT NULL DEFAULT 'knowledge-relations-v2',
                enabled INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(provider, language, query_key, version))"""
            )
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(knowledge_cache)")
            }
            migrations = {
                "validated": "INTEGER NOT NULL DEFAULT 1",
                "stale_until": "TEXT",
                "last_accessed_at": "TEXT",
                "schema_version": f"INTEGER NOT NULL DEFAULT {CACHE_SCHEMA_VERSION}",
                "rules_version": f"TEXT NOT NULL DEFAULT '{RELATION_RULES_VERSION}'",
                "enabled": "INTEGER NOT NULL DEFAULT 1",
            }
            for name, definition in migrations.items():
                if name not in columns:
                    connection.execute(
                        f"ALTER TABLE knowledge_cache ADD COLUMN {name} {definition}"
                    )
            connection.execute(
                "UPDATE knowledge_cache SET stale_until=expires_at WHERE stale_until IS NULL"
            )
            connection.execute(
                "UPDATE knowledge_cache SET last_accessed_at=created_at "
                "WHERE last_accessed_at IS NULL"
            )

    def _get(
        self,
        provider: str,
        language: str,
        query: str,
        version: str,
        *,
        stale: bool,
        now: datetime | None,
    ) -> KnowledgeExpansionResult | None:
        if not self.available:
            return None
        current = now or datetime.now(UTC)
        try:
            with self._lock, self._connect() as connection:
                row = connection.execute(
                    "SELECT status,candidates_json,degraded,warning,expires_at,stale_until,"
                    "validated,schema_version,rules_version,enabled FROM knowledge_cache "
                    "WHERE provider=? AND language=? AND query_key=? AND version=?",
                    (provider, language, normalized_query_key(query), version),
                ).fetchone()
                if row is None:
                    return None
                fresh_until, stale_until = _as_utc(row[4]), _as_utc(row[5])
                in_window = fresh_until <= current < stale_until if stale else current < fresh_until
                if (
                    not in_window
                    or not bool(row[6])
                    or row[7] != CACHE_SCHEMA_VERSION
                    or row[8] != RELATION_RULES_VERSION
                    or not bool(row[9])
                ):
                    return None
                candidates = [
                    KnowledgeExpansionCandidate.model_validate(item)
                    for item in json.loads(row[1])
                ]
                allowed = ALLOWED_RELATIONS.get(provider)
                if allowed is not None and any(item.relation not in allowed for item in candidates):
                    return None
                if any(item.source not in {provider, "cache"} for item in candidates):
                    return None
                result = KnowledgeExpansionResult.model_validate(
                    {
                        "provider": provider,
                        "status": row[0],
                        "candidates": [
                            item.model_copy(update={"source": "cache"}) for item in candidates
                        ],
                        "version": version,
                        "degraded": bool(row[2]) or stale,
                        "warning": row[3],
                    }
                )
                connection.execute(
                    "UPDATE knowledge_cache SET last_accessed_at=? "
                    "WHERE provider=? AND language=? AND query_key=? AND version=?",
                    (
                        current.isoformat(),
                        provider,
                        language,
                        normalized_query_key(query),
                        version,
                    ),
                )
                return result
        except (OSError, sqlite3.Error, TypeError, ValueError, json.JSONDecodeError):
            return None

    def get_fresh(
        self,
        provider: str,
        language: str,
        query: str,
        version: str,
        now: datetime | None = None,
    ) -> KnowledgeExpansionResult | None:
        return self._get(provider, language, query, version, stale=False, now=now)

    def get_stale(
        self,
        provider: str,
        language: str,
        query: str,
        version: str,
        now: datetime | None = None,
    ) -> KnowledgeExpansionResult | None:
        return self._get(provider, language, query, version, stale=True, now=now)

    def get(
        self, provider: str, language: str, query: str, version: str
    ) -> KnowledgeExpansionResult | None:
        """Compatibility alias for callers that only understand fresh cache entries."""
        return self.get_fresh(provider, language, query, version)

    def put(
        self,
        provider: str,
        language: str,
        query: str,
        result: KnowledgeExpansionResult,
        expires_at: datetime,
        stale_until: datetime | None = None,
    ) -> bool:
        if not self.available or result.provider != provider:
            return False
        stale_deadline = stale_until or expires_at
        if stale_deadline < expires_at:
            return False
        candidates = [
            item.model_copy(update={"derived_from": ["query-key"] if item.derived_from else []})
            for item in result.candidates
        ]
        allowed = ALLOWED_RELATIONS.get(provider)
        if allowed is not None and any(item.relation not in allowed for item in candidates):
            return False
        payload = json.dumps(
            [item.model_dump(mode="json") for item in candidates], ensure_ascii=False
        )
        now = datetime.now(UTC).isoformat()
        try:
            with self._lock, self._connect() as connection:
                connection.execute(
                    """INSERT OR REPLACE INTO knowledge_cache (
                    provider,language,query_key,version,status,candidates_json,degraded,warning,
                    created_at,expires_at,validated,stale_until,last_accessed_at,schema_version,
                    rules_version,enabled) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        provider,
                        language,
                        normalized_query_key(query),
                        result.version,
                        result.status,
                        payload,
                        int(result.degraded),
                        result.warning,
                        now,
                        expires_at.astimezone(UTC).isoformat(),
                        1,
                        stale_deadline.astimezone(UTC).isoformat(),
                        now,
                        CACHE_SCHEMA_VERSION,
                        RELATION_RULES_VERSION,
                        1,
                    ),
                )
            return True
        except (OSError, sqlite3.Error):
            return False

    def cleanup(self, now: datetime | None = None) -> int:
        if not self.available:
            return 0
        try:
            with self._lock, self._connect() as connection:
                cursor = connection.execute(
                    "DELETE FROM knowledge_cache WHERE stale_until <= ?",
                    ((now or datetime.now(UTC)).isoformat(),),
                )
                return cursor.rowcount
        except (OSError, sqlite3.Error):
            return 0
