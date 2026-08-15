from __future__ import annotations

from ragtorch.core.metrics import MetricsCollector


def test_record_and_values():
    m = MetricsCollector()
    m.record("latency", 1.0)
    m.record("latency", 2.0)
    assert m.values("latency") == [1.0, 2.0]


def test_values_for_unknown_metric_is_empty():
    m = MetricsCollector()
    assert m.values("nope") == []


def test_increment_defaults_to_one():
    m = MetricsCollector()
    m.increment("calls")
    m.increment("calls")
    assert m.values("calls") == [1, 1]


def test_increment_with_amount():
    m = MetricsCollector()
    m.increment("tokens", 42)
    assert m.values("tokens") == [42]


def test_names_lists_recorded_metrics():
    m = MetricsCollector()
    m.record("latency", 1.0)
    m.record("cost", 0.01)
    assert set(m.names()) == {"latency", "cost"}


def test_summarize_unknown_metric_returns_none():
    m = MetricsCollector()
    assert m.summarize("nope") is None


def test_summarize_single_sample():
    m = MetricsCollector()
    m.record("latency", 5.0)
    summary = m.summarize("latency")
    assert summary is not None
    assert summary.count == 1
    assert summary.sum == 5.0
    assert summary.min == summary.max == 5.0
    assert summary.p50 == summary.p95 == summary.p99 == 5.0


def test_summarize_multiple_samples():
    m = MetricsCollector()
    for v in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]:
        m.record("latency", v)
    summary = m.summarize("latency")
    assert summary is not None
    assert summary.count == 10
    assert summary.sum == 55
    assert summary.min == 1
    assert summary.max == 10
    assert summary.p50 == 6  # index 5 of sorted 1..10 (0-indexed)


def test_summarize_all_covers_every_recorded_metric():
    m = MetricsCollector()
    m.record("latency", 1.0)
    m.record("cost", 0.5)
    summaries = m.summarize_all()
    assert set(summaries) == {"latency", "cost"}
    assert summaries["latency"].count == 1
