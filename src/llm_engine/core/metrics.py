"""Lightweight in-memory metrics collector."""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MetricEvent:
    name: str
    value: float
    tags: dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class MetricsCollector:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, float] = defaultdict(float)
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._events: list[MetricEvent] = []

    def increment(self, name: str, value: float = 1.0, **tags: str) -> None:
        with self._lock:
            self._counters[name] += value
            self._events.append(MetricEvent(name=name, value=value, tags=tags))

    def observe(self, name: str, value: float, **tags: str) -> None:
        with self._lock:
            self._histograms[name].append(value)
            self._events.append(MetricEvent(name=name, value=value, tags=tags))

    def timer(self, name: str, **tags: str) -> _Timer:
        return _Timer(self, name, tags)

    def summary(self) -> dict[str, Any]:
        with self._lock:
            result: dict[str, Any] = {"counters": dict(self._counters)}
            histograms: dict[str, dict[str, float | int]] = {}
            for name, values in self._histograms.items():
                if not values:
                    continue
                sorted_values = sorted(values)
                histograms[name] = {
                    "count": len(values),
                    "min": sorted_values[0],
                    "max": sorted_values[-1],
                    "mean": sum(values) / len(values),
                    "p50": sorted_values[len(sorted_values) // 2],
                    "p95": sorted_values[int(len(sorted_values) * 0.95)],
                }
            result["histograms"] = histograms
            return result

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._histograms.clear()
            self._events.clear()

    def flush(self) -> None:
        summary = self.summary()
        if summary["counters"] or summary["histograms"]:
            logger.info(
                "metrics_flush counters=%s histograms=%d",
                dict(summary["counters"]),
                len(summary["histograms"]),
            )


class _Timer:
    def __init__(self, collector: MetricsCollector, name: str, tags: dict[str, str]) -> None:
        self._collector = collector
        self._name = name
        self._tags = tags
        self._start = 0.0

    def __enter__(self) -> _Timer:
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc: Any) -> None:
        elapsed = time.perf_counter() - self._start
        self._collector.observe(self._name, elapsed, **self._tags)


_global_metrics: MetricsCollector | None = None


def get_metrics() -> MetricsCollector:
    global _global_metrics
    if _global_metrics is None:
        _global_metrics = MetricsCollector()
    return _global_metrics
