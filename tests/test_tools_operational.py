"""Contract tests for query_logs, get_metrics, get_service_dependencies."""

from __future__ import annotations

from datetime import UTC, datetime

from opspilot.tools.contracts import DependencyEdge, LogRecord, MetricSample
from opspilot.tools.service import ToolService

SVC = ToolService()


def _dt(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


# --- query_logs -------------------------------------------------------------------------------
def test_query_logs_surfaces_signal_event():
    r = SVC.query_logs(service="payment-api", start_time=_dt("2026-06-28T09:45:00Z"),
                       end_time=_dt("2026-06-28T10:45:00Z"))
    assert r.status == "ok" and r.results
    assert all(isinstance(x, LogRecord) for x in r.results)
    assert all(ref.startswith("logs:payment-api:") for ref in r.evidence_refs)
    assert "logs:payment-api:evt-004-02" in r.evidence_refs  # the inc-004 signal


def test_query_logs_level_filter():
    r = SVC.query_logs(service="payment-api", level="error",
                       start_time=_dt("2026-06-28T09:45:00Z"), end_time=_dt("2026-06-28T10:45:00Z"))
    assert r.status == "ok" and all(x.level == "error" for x in r.results)


def test_query_logs_unknown_service_empty():
    r = SVC.query_logs(service="nope-api")
    assert r.status == "ok" and r.results == []


def test_query_logs_invalid_input_error():
    assert SVC.query_logs(service="").status == "error"


# --- get_metrics ------------------------------------------------------------------------------
def test_get_metrics_ref_matches_answer_key_exactly():
    r = SVC.get_metrics(
        service="payment-api", metric="p95_latency_ms",
        start_time=_dt("2026-06-28T09:45:00Z"), end_time=_dt("2026-06-28T10:45:00Z"))
    assert r.status == "ok" and r.results
    assert all(isinstance(x, MetricSample) for x in r.results)
    assert "metrics:payment-api:p95_latency_ms@2026-06-28T10:15:00Z" in r.evidence_refs


def test_get_metrics_all_metrics_for_infra_entity():
    r = SVC.get_metrics(service="cosmos-db")
    assert r.status == "ok" and {x.metric for x in r.results} >= {"ru_throttled_rate"}


def test_get_metrics_bad_window_error():
    r = SVC.get_metrics(service="payment-api", start_time=_dt("2026-06-28T11:00:00Z"),
                        end_time=_dt("2026-06-28T10:00:00Z"))
    assert r.status == "error"


# --- get_service_dependencies -----------------------------------------------------------------
def test_dependencies_full_graph():
    r = SVC.get_service_dependencies()
    assert r.status == "ok" and len(r.results) >= 12
    assert all(isinstance(e, DependencyEdge) for e in r.results)
    assert "deps:checkout-api->payment-api" in r.evidence_refs


def test_dependencies_downstream_and_critical():
    r = SVC.get_service_dependencies(service="checkout-api", direction="downstream")
    assert r.status == "ok" and all(e.from_service == "checkout-api" for e in r.results)
    edge = next(e for e in r.results if e.to_service == "payment-api")
    assert edge.critical is True


def test_dependencies_upstream_filter():
    r = SVC.get_service_dependencies(service="cosmos-db", direction="upstream")
    assert r.status == "ok" and r.results
    assert all(e.to_service == "cosmos-db" for e in r.results)


def test_service_now_exposes_six_tools():
    assert set(SVC.tool_names) == {
        "get_incident", "get_correlated_alerts", "get_deployments",
        "query_logs", "get_metrics", "get_service_dependencies",
    }
