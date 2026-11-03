from tools.smolvla_smoke import latency_stats


def test_latency_stats_does_not_hide_chunk_boundary_stall():
    report = latency_stats([1.0] * 49 + [400.0])
    assert report["mean_ms"] < 50
    assert report["max_ms"] == 400
    assert report["over_budget_count"] == 1
    assert report["over_budget_fraction"] == 0.02


def test_latency_stats_50ms_is_within_budget():
    report = latency_stats([50.0, 51.0])
    assert report["over_budget_count"] == 1
    assert report["p50_ms"] == 50.5
    assert report["p95_ms"] == 50.95
