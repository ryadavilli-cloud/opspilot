"""Observability emission seam (Stage 5g) — spans emitted ONCE at the shared primitives.

Per code-guidelines §23 and adr-observability-tracing.md: a new node / tool / LLM / MCP call
inherits a span for free; hand-instrumenting an individual node is prohibited. Spans are OTLP-shaped
(`trace_id` / `span_id` / `parent_span_id` / name / attributes / timing / status) and go to a
config-selected exporter (`none` in prod until a real sink is wired, `memory` for tests, `stdout`
for dev). Spans are NOT behaviour-affecting inputs, so this adds zero cassette churn —
instrumentation may land at any stage with no re-record.

This module is the seam itself + the node-dispatch wrapper. The `run_tool`/`gateway`, `ChatModel`,
and MCP wrappers are the remaining primitives (following slices); each reuses `span()` here, never
its own bespoke tracing.
"""

from __future__ import annotations

import contextlib
import contextvars
import functools
import inspect
import json
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from opspilot import config


@dataclass
class Span:
    """One OTLP-shaped span. `attributes` carries the §23 standard set plus primitive specifics."""

    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    attributes: dict[str, Any] = field(default_factory=dict)
    start_ms: float = 0.0
    end_ms: float = 0.0
    status: str = "ok"  # ok | error

    @property
    def latency_ms(self) -> float:
        return round(self.end_ms - self.start_ms, 3)


class SpanExporter(Protocol):
    def export(self, span: Span) -> None: ...


class InMemorySpanExporter:
    """Collects spans for assertions — the test fixture rides on this."""

    def __init__(self) -> None:
        self.spans: list[Span] = []

    def export(self, span: Span) -> None:
        self.spans.append(span)

    def clear(self) -> None:
        self.spans.clear()


class _NoopExporter:
    """Default in prod: emission is instrumented but no sink is attached until Stage 5g/11."""

    def export(self, span: Span) -> None:
        return


class _StdoutExporter:
    def export(self, span: Span) -> None:
        print(
            json.dumps(
                {
                    "span": span.name,
                    "trace_id": span.trace_id,
                    "span_id": span.span_id,
                    "parent_span_id": span.parent_span_id,
                    "status": span.status,
                    **span.attributes,
                }
            ),
            flush=True,
        )


_EXPORTERS: dict[str, Callable[[], SpanExporter]] = {
    "none": _NoopExporter,
    "memory": InMemorySpanExporter,
    "stdout": _StdoutExporter,
}

_exporter: SpanExporter = _NoopExporter()
_current_span: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "opspilot_current_span", default=None
)


def configure_exporter(exporter: SpanExporter | None = None) -> SpanExporter:
    """Set the process exporter. No arg → select by `OPSPILOT_TRACE_EXPORTER` (default `none`)."""
    global _exporter
    if exporter is not None:
        _exporter = exporter
    else:
        _exporter = _EXPORTERS.get(config.TRACE_EXPORTER, _NoopExporter)()
    return _exporter


def get_exporter() -> SpanExporter:
    return _exporter


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


def standard_attributes(state: Any) -> dict[str, Any]:
    """The run-level attributes every span carries (§23). Primitive wrappers add their specifics
    (tool_name/hashes/tokens/cost). Reads defensively so a partial state never breaks emission."""
    return {
        "investigation_id": getattr(state, "investigation_id", "") or "",
        "incident_id": getattr(state, "incident_id", "") or "",
        "workflow_version": getattr(state, "workflow_version", "") or "",
    }


@contextlib.contextmanager
def span(name: str, *, trace_id: str, attributes: dict[str, Any] | None = None) -> Iterator[Span]:
    """Emit one span under the current parent (contextvar-nested). Exported on exit, with `status`
    flipped to `error` if the body raised (the exception still propagates)."""
    sp = Span(
        trace_id=trace_id or "",
        span_id=_new_id(),
        parent_span_id=_current_span.get(),
        name=name,
        attributes=dict(attributes or {}),
        start_ms=time.monotonic() * 1000.0,
    )
    token = _current_span.set(sp.span_id)
    try:
        yield sp
    except BaseException:
        sp.status = "error"
        raise
    finally:
        sp.end_ms = time.monotonic() * 1000.0
        sp.attributes.setdefault("latency_ms", sp.latency_ms)
        _current_span.reset(token)
        _exporter.export(sp)


def traced_node(name: str, fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """Wrap a graph node so every dispatch emits a span under the run's `trace_id` — one wrapper for
    all nodes, so a new node is traced with no per-site code (§23).

    LangGraph injects the `RunnableConfig` (which carries the per-run `ToolService` etc.) into nodes
    that declare a `config` parameter, and it decides that by INSPECTING THE SIGNATURE. So the
    wrapper preserves the wrapped node's signature (`functools.wraps` → `inspect.signature` follows
    `__wrapped__`) and forwards `config` — otherwise LangGraph would not inject it and the node
    falls back to a default service. The node's own return is untouched; a returned `error`/degraded
    flag is reflected onto the span status."""
    accepts_config = "config" in inspect.signature(fn).parameters

    @functools.wraps(fn)
    def wrapped(state: Any, config: Any = None) -> dict[str, Any]:
        trace_id = getattr(state, "trace_id", "") or getattr(state, "investigation_id", "") or ""
        attrs = {**standard_attributes(state), "node": name}
        with span(f"node.{name}", trace_id=trace_id, attributes=attrs) as sp:
            result = fn(state, config) if accepts_config else fn(state)
            if isinstance(result, dict) and (result.get("error") or result.get("degraded")):
                sp.status = "error"
                if result.get("error"):
                    sp.attributes["reason"] = result["error"]
            return result

    return wrapped
