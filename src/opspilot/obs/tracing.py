"""Observability emission seam: spans emitted ONCE at the shared primitives.

A new node / tool / LLM / MCP call inherits a span for free; hand-instrumenting an individual node
is prohibited, because instrumentation built per call site drifts and drifted attributes cannot be
correlated. Spans are OTLP-shaped
(`trace_id` / `span_id` / `parent_span_id` / name / attributes / timing / status) and go to a
config-selected exporter (`none` in prod until a real sink is wired, `memory` for tests, `stdout`
for dev). Spans are NOT behaviour-affecting inputs, so this adds zero cassette churn —
instrumentation may land at any stage with no re-record.

This module is the seam itself + the node-dispatch wrapper. The `run_tool`/`gateway`, `ChatModel`,
and MCP wrappers are the remaining primitives; each reuses `span()` here, never its own bespoke
tracing.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from opspilot import config


@dataclass
class Span:
    """One OTLP-shaped span. `attributes` carries the standard set plus primitive specifics."""

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
    """Default in prod: emission is instrumented but no sink is attached."""

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
# The run's trace_id, propagated down the call tree so nested primitives (tool / model / MCP spans)
# inherit it without threading state through every call. The node wrapper establishes it from state.
_current_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "opspilot_current_trace_id", default=""
)
# The correlation attributes every span inside an investigation must carry. Propagated down the
# call tree so a nested primitive is attributed without its call site knowing which investigation
# it belongs to: `trace_id` alone would leave a child diagnosable only by first finding its root
# and reading the identity off that, which is reassembly at read time rather than context attached
# where the work entered the boundary.
_CORRELATION_KEYS = ("investigation_id", "incident_id")
_current_correlation: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(
    "opspilot_current_correlation", default=None
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


@contextlib.contextmanager
def span(
    name: str, *, trace_id: str = "", attributes: dict[str, Any] | None = None
) -> Iterator[Span]:
    """Emit one span under the current parent (contextvar-nested). `trace_id` defaults to the
    current run's id from the context, so nested primitive spans (tool/model/MCP) inherit it —
    pass it explicitly only at the root (the node wrapper). Exported on exit, with `status`
    flipped to `error` if the body raised (the exception still propagates).

    `investigation_id` and `turn_id` are inherited from the enclosing span the same way, so every
    span emitted inside a turn carries them without its call site passing them. A span that names
    either explicitly wins, and an empty value never propagates: an absent identity stays absent
    rather than overwriting a real one further down."""
    resolved_trace = trace_id or _current_trace_id.get()
    inherited = _current_correlation.get() or {}
    merged = {**inherited, **(attributes or {})}
    # `standard_attributes` reads defensively and yields "" for an identity its state does not
    # carry. An explicit blank must not erase an identity the enclosing turn already established.
    for key in _CORRELATION_KEYS:
        if not merged.get(key) and inherited.get(key):
            merged[key] = inherited[key]
    sp = Span(
        trace_id=resolved_trace,
        span_id=_new_id(),
        parent_span_id=_current_span.get(),
        name=name,
        attributes=merged,
        start_ms=time.monotonic() * 1000.0,
    )
    span_token = _current_span.set(sp.span_id)
    trace_token = _current_trace_id.set(resolved_trace)
    carried = {key: merged[key] for key in _CORRELATION_KEYS if merged.get(key)}
    correlation_token = _current_correlation.set(carried)
    try:
        yield sp
    except BaseException:
        sp.status = "error"
        raise
    finally:
        sp.end_ms = time.monotonic() * 1000.0
        sp.attributes.setdefault("latency_ms", sp.latency_ms)
        _current_span.reset(span_token)
        _current_trace_id.reset(trace_token)
        _current_correlation.reset(correlation_token)
        _exporter.export(sp)
