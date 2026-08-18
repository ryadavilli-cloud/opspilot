"""The emission seam: OTLP-shaped spans nested under the parent trace id.

A missing or broken trace is a silent failure exactly when it is needed most, so it is tested
rather than assumed."""

from __future__ import annotations

import pytest

from opspilot.obs import tracing


def test_span_carries_what_the_caller_states(span_exporter: tracing.InMemorySpanExporter):
    with tracing.span("unit", trace_id="t-1", attributes={"node": "diagnose", "k": "v"}) as sp:
        assert sp.trace_id == "t-1"
    assert len(span_exporter.spans) == 1
    got = span_exporter.spans[0]
    assert got.name == "unit" and got.trace_id == "t-1" and got.status == "ok"
    assert got.attributes["node"] == "diagnose"
    assert "latency_ms" in got.attributes and got.attributes["latency_ms"] >= 0.0


def test_nested_spans_link_to_parent(span_exporter: tracing.InMemorySpanExporter):
    with tracing.span("parent", trace_id="t-1"):
        with tracing.span("child", trace_id="t-1"):
            pass
    by_name = {s.name: s for s in span_exporter.spans}
    assert by_name["parent"].parent_span_id is None
    assert by_name["child"].parent_span_id == by_name["parent"].span_id


def test_span_status_error_on_exception_and_reraises(span_exporter: tracing.InMemorySpanExporter):
    with pytest.raises(ValueError):
        with tracing.span("boom", trace_id="t-1"):
            raise ValueError("nope")
    assert span_exporter.spans[0].status == "error"


def test_tool_span_nests_under_node_and_inherits_trace(span_exporter):
    from opspilot.tools.errors import run_tool, validated

    @validated
    def _capability(source: str, deadline_s: float, *, x: int = 0) -> tuple[list[dict], list[str]]:
        return [{"a": x}], ["metrics:m-1"]

    with tracing.span("node.diagnose", trace_id="t-9"):
        run_tool("get_metrics", _capability, "source", 1.0, x=1)

    tool = next(s for s in span_exporter.spans if s.name == "tool.get_metrics")
    node = next(s for s in span_exporter.spans if s.name == "node.diagnose")
    assert tool.trace_id == "t-9"  # inherited from the node via the trace context
    assert tool.parent_span_id == node.span_id  # nested under the node span
    assert tool.attributes["tool_name"] == "get_metrics"
    assert tool.attributes["execution_outcome"] == "succeeded"
    assert tool.attributes["completeness"] == "complete"
    assert tool.attributes["result_count"] == 1


def test_model_span_captures_usage(span_exporter):
    from opspilot.llm.base import ChatMessage, ChatResult
    from opspilot.llm.client import TracedChatModel

    class _Model:
        deployment = "gpt-5-mini"

        def complete(self, task, messages):
            return ChatResult(
                text="ok",
                task=task,
                deployment="gpt-5-mini",
                finish_reason="stop",
                latency_ms=41.5,
                usage={"prompt_tokens": 12, "completion_tokens": 5},
            )

    with tracing.span("node.diagnose", trace_id="t-9"):
        TracedChatModel(_Model()).complete("rca_synthesis", [ChatMessage("user", "hi")])

    model = next(s for s in span_exporter.spans if s.name == "model.complete")
    assert model.trace_id == "t-9" and model.attributes["model_deployment"] == "gpt-5-mini"
    assert model.attributes["tokens_in"] == 12 and model.attributes["tokens_out"] == 5
    # The task the call served and what it cost in wall time, both from what the seam reported.
    assert model.attributes["task"] == "rca_synthesis"
    assert model.attributes["latency_ms"] == 41.5
