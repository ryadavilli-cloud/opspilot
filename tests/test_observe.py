"""Tool-result summarizers (Stage 4b) — no ML stack.

The summary must surface the values a model needs to reason AND the exact citable ref, while
collapsing noise (many near-identical log lines) so it does not crowd the prompt.
"""

from __future__ import annotations

from datetime import UTC, datetime

from opspilot.diagnosis.observe import summarize
from opspilot.tools.contracts import DeploymentRecord, LogRecord, MetricSample


def _ts(hour: int, minute: int) -> datetime:
    return datetime(2026, 6, 28, hour, minute, tzinfo=UTC)


def test_metrics_summary_shows_peak_value_and_ref():
    samples = [
        MetricSample(service="payment-api", metric="p95_latency_ms", ts=_ts(10, 0),
                     value=50.0, unit="ms"),
        MetricSample(service="payment-api", metric="p95_latency_ms", ts=_ts(10, 10),
                     value=820.0, unit="ms"),
    ]
    refs = ["metrics:payment-api:p95_latency_ms@a", "metrics:payment-api:p95_latency_ms@b"]
    out = summarize("get_metrics", samples, refs)
    assert "820" in out                                     # the model sees the value...
    assert "[metrics:payment-api:p95_latency_ms@b]" in out  # ...tied to the peak sample's ref


def test_logs_summary_collapses_noise_but_keeps_signal_ref():
    logs = [LogRecord(event_id="evt-004-02", ts=_ts(10, 14), service="payment-api",
                      level="error", message="PaymentGatewayTimeout calling external gateway")]
    logs += [LogRecord(event_id=f"noise-{i}", ts=_ts(10, 15), service="payment-api",
                       level="error", message="request retried") for i in range(12)]
    refs = [f"logs:payment-api:{log.event_id}" for log in logs]
    out = summarize("query_logs", logs, refs)
    assert "13 logs" in out
    assert "PaymentGatewayTimeout" in out
    assert "[logs:payment-api:evt-004-02]" in out           # the signal ref is surfaced
    assert "×12" in out                                     # the noise is collapsed, not dumped


def test_summary_is_defensive_on_empty_and_unknown():
    assert summarize("get_metrics", [], []) == "no results"
    dep = DeploymentRecord(deploy_id="d1", service="checkout-api", ts=_ts(9, 0),
                           version="5.7.2", note="routine")
    assert "d1" in summarize("get_deployments", [dep], ["deploys:checkout-api:d1"])
