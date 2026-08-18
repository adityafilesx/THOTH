from omnimac_daemon.voice.metrics import VoiceLatencyMetrics, VoiceLatencyStage


def test_latency_metrics_are_bounded_and_report_p50_p95() -> None:
    metrics = VoiceLatencyMetrics(max_samples_per_stage=5)
    for value in (1, 2, 3, 4, 100, 200):
        metrics.record(VoiceLatencyStage.REFLEX_ROUTE, value)

    snapshot = metrics.snapshot()
    sample = snapshot.stages[VoiceLatencyStage.REFLEX_ROUTE]
    assert sample.count == 5
    assert sample.p50_ms == 4
    assert sample.p95_ms == 200
    assert sample.last_ms == 200


def test_latency_metrics_reject_negative_measurements() -> None:
    metrics = VoiceLatencyMetrics()

    try:
        metrics.record(VoiceLatencyStage.STOP_ACKNOWLEDGEMENT, -1)
    except ValueError as exc:
        assert "non-negative" in str(exc)
    else:
        raise AssertionError("negative latency was accepted")
