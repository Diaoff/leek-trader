from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from time import perf_counter
from typing import Literal

ProviderHealthStatus = Literal["success", "empty", "failure"]
RuntimeHealthLevel = Literal["healthy", "degraded", "down", "unknown"]


@dataclass(frozen=True, slots=True)
class ProviderHealthEvent:
    source: str
    operation: str
    status: ProviderHealthStatus
    latency_ms: float | None = None
    row_count: int | None = None
    error_message: str | None = None
    recorded_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ProviderHealthSummary:
    source: str
    last_success_at: str | None
    last_failure_at: str | None
    recent_failure_count: int
    recent_empty_count: int
    avg_latency_ms: float | None
    runtime_health_level: RuntimeHealthLevel


class ProviderHealthTracker:
    def __init__(self, *, max_events: int = 500, failure_down_threshold: int = 3) -> None:
        self.max_events = max_events
        self.failure_down_threshold = failure_down_threshold
        self._events: deque[ProviderHealthEvent] = deque(maxlen=max_events)
        self._lock = Lock()

    def record(
        self,
        *,
        source: str,
        operation: str,
        status: ProviderHealthStatus,
        latency_ms: float | None = None,
        row_count: int | None = None,
        error_message: str | None = None,
        recorded_at: datetime | None = None,
    ) -> ProviderHealthEvent:
        event = ProviderHealthEvent(
            source=source,
            operation=operation,
            status=status,
            latency_ms=round(float(latency_ms), 3) if latency_ms is not None else None,
            row_count=row_count,
            error_message=error_message,
            recorded_at=recorded_at or datetime.now(UTC),
        )
        with self._lock:
            self._events.append(event)
        return event

    def summary(self, source: str) -> ProviderHealthSummary:
        with self._lock:
            events = [event for event in self._events if event.source == source]
        if not events:
            return ProviderHealthSummary(
                source=source,
                last_success_at=None,
                last_failure_at=None,
                recent_failure_count=0,
                recent_empty_count=0,
                avg_latency_ms=None,
                runtime_health_level="unknown",
            )
        successes = [event for event in events if event.status == "success"]
        failures = [event for event in events if event.status == "failure"]
        empties = [event for event in events if event.status == "empty"]
        latencies = [event.latency_ms for event in events if event.latency_ms is not None]
        consecutive_failures = 0
        for event in reversed(events):
            if event.status != "failure":
                break
            consecutive_failures += 1
        if consecutive_failures >= self.failure_down_threshold:
            level: RuntimeHealthLevel = "down"
        elif failures or empties:
            level = "degraded"
        else:
            level = "healthy"
        return ProviderHealthSummary(
            source=source,
            last_success_at=self._latest_iso(successes),
            last_failure_at=self._latest_iso(failures),
            recent_failure_count=len(failures),
            recent_empty_count=len(empties),
            avg_latency_ms=round(sum(latencies) / len(latencies), 3) if latencies else None,
            runtime_health_level=level,
        )

    def reset(self) -> None:
        with self._lock:
            self._events.clear()

    @staticmethod
    def _latest_iso(events: list[ProviderHealthEvent]) -> str | None:
        if not events:
            return None
        recorded_at = events[-1].recorded_at
        return recorded_at.isoformat() if recorded_at else None


provider_health_tracker = ProviderHealthTracker()


def record_provider_call(source: str, operation: str, started_at: float, row_count: int | None = None, error: Exception | None = None) -> None:
    latency_ms = (perf_counter() - started_at) * 1000
    if error is not None:
        provider_health_tracker.record(
            source=source,
            operation=operation,
            status="failure",
            latency_ms=latency_ms,
            row_count=row_count,
            error_message=str(error),
        )
        return
    provider_health_tracker.record(
        source=source,
        operation=operation,
        status="success" if row_count else "empty",
        latency_ms=latency_ms,
        row_count=row_count,
    )
