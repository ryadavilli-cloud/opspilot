"""Uniform envelope assembly: validate, time, cap, sanitize — no exception escapes a tool.

`run_tool` is the single boundary every tool goes through. It validates raw kwargs into the
request model, runs the tool's pure logic (which returns `(records, evidence_refs)`), applies the
result cap, and stamps timing metadata. Bad input or bad data becomes a `status="error"` envelope
with a short, sanitized message — never a raised exception, stack trace, or leaked path.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from opspilot.tools.contracts import MAX_RESULTS, ToolMetadata, ToolResult


def sanitize(exc: Exception) -> str:
    """A short, caller-safe message. Validation errors are summarized; nothing else is detailed."""
    if isinstance(exc, ValidationError):
        parts = []
        for err in exc.errors():
            loc = ".".join(str(x) for x in err.get("loc", ())) or "input"
            parts.append(f"{loc}: {err.get('msg', 'invalid')}")
        return "invalid request — " + "; ".join(parts)
    return "invalid request"


def _metadata(tool_name: str, started: float, count: int, truncated: bool = False) -> ToolMetadata:
    return ToolMetadata(
        tool_name=tool_name,
        duration_ms=round((time.perf_counter() - started) * 1000, 3),
        result_count=count,
        truncated=truncated,
    )


def error_result(tool_name: str, message: str, started: float) -> ToolResult[Any]:
    return ToolResult(
        tool_name=tool_name, status="error", error=message,
        metadata=_metadata(tool_name, started, 0),
    )


def run_tool(
    tool_name: str,
    request_cls: type[BaseModel],
    logic: Callable[[Any], tuple[list, list[str]]],
    **kwargs: Any,
) -> ToolResult[Any]:
    started = time.perf_counter()
    try:
        request = request_cls(**kwargs)
    except ValidationError as exc:
        return error_result(tool_name, sanitize(exc), started)
    except Exception:  # noqa: BLE001 — no exception may cross the tool boundary, even from a validator
        return error_result(tool_name, "invalid request", started)
    try:
        records, evidence_refs = logic(request)
    except Exception:  # noqa: BLE001 — no exception may cross the tool boundary
        return error_result(tool_name, "internal tool error", started)
    truncated = len(records) > MAX_RESULTS
    records = records[:MAX_RESULTS]
    return ToolResult(
        tool_name=tool_name, status="ok", results=records, evidence_refs=evidence_refs,
        metadata=_metadata(tool_name, started, len(records), truncated),
    )
