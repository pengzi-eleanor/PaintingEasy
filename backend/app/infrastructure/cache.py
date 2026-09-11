from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Generic, Protocol, TypeVar

T = TypeVar("T")


class Cache(Protocol[T]):
    def get(self, key: str) -> T | None: ...

    def set(self, key: str, value: T) -> None: ...


@dataclass
class _Entry(Generic[T]):
    value: T
    expires_at: float


class InMemoryTTLCache(Generic[T]):
    """Small process-local LRU/TTL cache for provider or search results."""

    def __init__(self, *, max_entries: int = 256, ttl_seconds: float = 900):
        self.max_entries = max(0, max_entries)
        self.ttl_seconds = max(0, ttl_seconds)
        self._entries: OrderedDict[str, _Entry[T]] = OrderedDict()
        self._lock = Lock()

    def get(self, key: str) -> T | None:
        if not self.max_entries or not self.ttl_seconds:
            return None
        now = monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._entries.pop(key, None)
                return None
            self._entries.move_to_end(key)
            return entry.value

    def set(self, key: str, value: T) -> None:
        if not self.max_entries or not self.ttl_seconds:
            return
        with self._lock:
            self._entries[key] = _Entry(value, monotonic() + self.ttl_seconds)
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
