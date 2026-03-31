"""metrics.py 단위 테스트."""

from __future__ import annotations

import time

from LLMEngine.core.metrics import MetricsCollector


class TestMetricsCollector:
    def test_increment(self):
        m = MetricsCollector()
        m.increment("calls")
        m.increment("calls", 2.0)
        assert m.summary()["counters"]["calls"] == 3.0

    def test_observe(self):
        m = MetricsCollector()
        m.observe("duration", 1.5)
        m.observe("duration", 2.5)
        s = m.summary()["histograms"]["duration"]
        assert s["count"] == 2
        assert s["min"] == 1.5
        assert s["max"] == 2.5
        assert abs(s["mean"] - 2.0) < 0.01

    def test_timer(self):
        m = MetricsCollector()
        with m.timer("operation"):
            time.sleep(0.01)
        s = m.summary()["histograms"]["operation"]
        assert s["count"] == 1
        assert s["min"] > 0

    def test_reset(self):
        m = MetricsCollector()
        m.increment("x")
        m.observe("y", 1.0)
        m.reset()
        s = m.summary()
        assert s["counters"] == {}
        assert s["histograms"] == {}

    def test_flush_no_error(self):
        m = MetricsCollector()
        m.increment("test")
        m.flush()

    def test_empty_summary(self):
        m = MetricsCollector()
        s = m.summary()
        assert s["counters"] == {}
        assert s["histograms"] == {}

    def test_tags_preserved(self):
        m = MetricsCollector()
        m.increment("calls", model="gpt-4o")
        assert len(m._events) == 1
        assert m._events[0].tags["model"] == "gpt-4o"
