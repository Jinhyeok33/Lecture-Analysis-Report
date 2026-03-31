"""경량 메트릭 수집 인프라.

운영 환경에서 Prometheus/OpenTelemetry 연동 전 사용할 수 있는
인메모리 메트릭 수집기. 파이프라인의 각 단계에서 시간, 재시도 횟수,
비용 등을 기록하고 요약 통계를 제공한다.

확장 포인트:
- MetricsCollector를 상속하여 PrometheusCollector, OTelCollector 등 구현 가능
- flush()를 오버라이드하여 외부 시스템으로 push 가능
"""

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
    """인메모리 메트릭 수집기.

    스레드 안전하며, 파이프라인 종료 후 summary()로 통계를 확인할 수 있다.
    """

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
        """히스토그램형 관측값 기록 (소요시간, 비용 등)."""
        with self._lock:
            self._histograms[name].append(value)
            self._events.append(MetricEvent(name=name, value=value, tags=tags))

    def timer(self, name: str, **tags: str) -> _Timer:
        """컨텍스트 매니저 기반 타이머."""
        return _Timer(self, name, tags)

    def summary(self) -> dict[str, Any]:
        """수집된 메트릭 요약 반환."""
        with self._lock:
            result: dict[str, Any] = {"counters": dict(self._counters)}
            hist_summary = {}
            for name, values in self._histograms.items():
                if values:
                    sorted_v = sorted(values)
                    hist_summary[name] = {
                        "count": len(values),
                        "min": sorted_v[0],
                        "max": sorted_v[-1],
                        "mean": sum(values) / len(values),
                        "p50": sorted_v[len(sorted_v) // 2],
                        "p95": sorted_v[int(len(sorted_v) * 0.95)],
                    }
            result["histograms"] = hist_summary
            return result

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._histograms.clear()
            self._events.clear()

    def flush(self) -> None:
        """외부 시스템으로 메트릭을 전송하는 확장 포인트.

        기본 구현은 로그에 요약을 출력한다. Prometheus/OTel 사용 시 오버라이드.
        """
        s = self.summary()
        if s["counters"] or s["histograms"]:
            logger.info("metrics_flush counters=%s histograms=%d",
                        dict(s["counters"]),
                        len(s["histograms"]))


class _Timer:
    """MetricsCollector.timer()용 컨텍스트 매니저."""

    def __init__(self, collector: MetricsCollector, name: str, tags: dict[str, str]) -> None:
        self._collector = collector
        self._name = name
        self._tags = tags
        self._start: float = 0.0

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
