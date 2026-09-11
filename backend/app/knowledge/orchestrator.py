from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import StrEnum

from app.models.schemas import KnowledgeExpansionRequest, KnowledgeExpansionResult

from .cache import normalized_query_key
from .providers import KnowledgeExpansionProvider

logger = logging.getLogger(__name__)


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class ReliabilityPolicy:
    retries: int = 1
    concurrency: int = 2
    failure_threshold: int = 3
    cooldown_seconds: float = 30
    coalesced_wait_seconds: float = 10


@dataclass
class _InFlight:
    event: threading.Event
    result: KnowledgeExpansionResult | None = None


class _ProviderState:
    def __init__(self, policy: ReliabilityPolicy):
        self.semaphore = threading.BoundedSemaphore(policy.concurrency)
        self.failures = 0
        self.opened_at = 0.0
        self.state = CircuitState.CLOSED
        self.probe_active = False
        self.inflight: dict[str, _InFlight] = {}
        self.lock = threading.RLock()


class ExternalKnowledgeOrchestrator:
    """Run independent providers concurrently without exposing query or exception details."""

    def __init__(
        self,
        providers: list[KnowledgeExpansionProvider],
        policy: ReliabilityPolicy | None = None,
        clock=time.monotonic,
    ):
        self.providers = providers
        self.policy = policy or ReliabilityPolicy()
        self.clock = clock
        self.states = {provider.name: _ProviderState(self.policy) for provider in providers}

    def expand(
        self, request: KnowledgeExpansionRequest
    ) -> tuple[list[KnowledgeExpansionResult], list[str]]:
        enabled = [provider for provider in self.providers if provider.enabled]
        if not enabled:
            return [], []

        results_by_name: dict[str, KnowledgeExpansionResult] = {}
        misses = []
        for provider in enabled:
            fresh = self._get_cached(provider, request, stale=False)
            if fresh is None:
                misses.append(provider)
            else:
                results_by_name[provider.name] = fresh

        if misses:
            with ThreadPoolExecutor(max_workers=len(misses)) as pool:
                futures = {
                    provider.name: pool.submit(self._call_live, provider, request)
                    for provider in misses
                }
                for provider in misses:
                    results_by_name[provider.name] = futures[provider.name].result()

        results = [results_by_name[provider.name] for provider in enabled]
        if not any(result.candidates for result in results):
            results = [
                result.model_copy(
                    update={
                        "source_status": "original_fallback",
                        "degraded": result.status in {"failed", "degraded"},
                    }
                )
                for result in results
            ]
        warnings = [
            f"{result.provider} 暂不可用，已保留其他关键词结果"
            for result in results
            if result.source_status == "original_fallback"
            and result.status in {"failed", "degraded"}
        ]
        return results, warnings

    @staticmethod
    def _get_cached(provider, request, *, stale: bool):
        method = getattr(provider, "get_stale" if stale else "get_fresh", None)
        return method(request) if method is not None else None

    def _call_live(
        self, provider: KnowledgeExpansionProvider, request: KnowledgeExpansionRequest
    ) -> KnowledgeExpansionResult:
        state = self.states[provider.name]
        request_key = normalized_query_key(request.query)
        with state.lock:
            existing = state.inflight.get(request_key)
            if existing is None:
                inflight = _InFlight(threading.Event())
                state.inflight[request_key] = inflight
                owner = True
            else:
                inflight = existing
                owner = False
        if not owner:
            if inflight.event.wait(self.policy.coalesced_wait_seconds) and inflight.result:
                return inflight.result
            return self._fallback(provider, request, "degraded")

        result: KnowledgeExpansionResult
        try:
            result = self._execute_owner(provider, request, state)
            return result
        finally:
            with state.lock:
                inflight.result = locals().get("result")
                inflight.event.set()
                state.inflight.pop(request_key, None)

    def _execute_owner(self, provider, request, state) -> KnowledgeExpansionResult:
        now = self.clock()
        with state.lock:
            if state.state == CircuitState.OPEN:
                if now - state.opened_at < self.policy.cooldown_seconds:
                    return self._fallback(provider, request, "degraded")
                state.state = CircuitState.HALF_OPEN
            if state.state == CircuitState.HALF_OPEN:
                if state.probe_active:
                    return self._fallback(provider, request, "degraded")
                state.probe_active = True

        if not state.semaphore.acquire(timeout=0.05):
            return self._fallback(provider, request, "degraded")
        try:
            for attempt in range(self.policy.retries + 1):
                try:
                    fetch_live = getattr(provider, "fetch_live", None)
                    result = fetch_live(request) if fetch_live else provider.expand(request)
                    if result.status in {"failed", "degraded"}:
                        raise RuntimeError("provider returned degraded status")
                    with state.lock:
                        state.failures = 0
                        state.state = CircuitState.CLOSED
                        state.probe_active = False
                    return result.model_copy(update={"source_status": "live"})
                except Exception as exc:
                    logger.warning(
                        "knowledge provider failed provider=%s type=%s attempt=%s",
                        provider.name,
                        type(exc).__name__,
                        attempt + 1,
                    )
            with state.lock:
                state.failures += 1
                state.probe_active = False
                if state.failures >= self.policy.failure_threshold:
                    state.state = CircuitState.OPEN
                    state.opened_at = self.clock()
            return self._fallback(provider, request, "failed", record_failure=True)
        finally:
            state.semaphore.release()

    def _fallback(
        self,
        provider,
        request: KnowledgeExpansionRequest,
        status: str,
        *,
        record_failure: bool = False,
    ) -> KnowledgeExpansionResult:
        stale = self._get_cached(provider, request, stale=True)
        if stale is not None:
            return stale.model_copy(update={"source_status": "stale_cache", "degraded": True})
        if record_failure:
            recorder = getattr(provider, "record_failure", None)
            if recorder is not None:
                recorder(request)
        return KnowledgeExpansionResult(
            provider=provider.name,
            status=status,
            version=provider.version,
            degraded=True,
            warning="外部知识扩展暂不可用",
            source_status="original_fallback",
        )
