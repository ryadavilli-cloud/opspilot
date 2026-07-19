"""Tool-result summarizers — turn raw records into a compact `signal [ref]` view for a model.

The diagnosis loop feeds the planner what a tool *found*, not just that it ran. A raw dump of every
evidence ref (14 log ids, ~40 metric samples, most of them noise) both hides the actual values and
crowds the prompt. These summarizers surface the values and the *one* citable ref per signal, so the
model can reason over data and cite precisely. Grounding is unchanged — every `[ref]` shown here is
a real tool-produced evidence ref (from `evidence_refs`), so a citation of it still validates.

Defensive by construction: any unexpected record shape falls back to a plain count, never raises
(this runs inside `run_cycle` for every tool call, deterministic and LLM alike).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

_MAX_LOG_GROUPS = 6
_MAX_ITEMS = 8


def _hm(ts: Any) -> str:
    try:
        return ts.strftime("%H:%M")
    except Exception:  # noqa: BLE001
        return str(ts)


def _pairs(results: list[Any], refs: list[str]) -> list[tuple[Any, str]]:
    return [(rec, refs[i] if i < len(refs) else "") for i, rec in enumerate(results)]


def _tag(ref: str) -> str:
    return f" [{ref}]" if ref else ""


def _metrics(results: list[Any], refs: list[str]) -> str:
    by_metric: dict[str, list[tuple[Any, str]]] = defaultdict(list)
    for rec, ref in _pairs(results, refs):
        by_metric[rec.metric].append((rec, ref))
    lines = []
    for metric, items in sorted(by_metric.items()):
        values = [r.value for r, _ in items]
        lo, hi = min(values), max(values)
        peak_rec, peak_ref = max(items, key=lambda p: p[0].value)
        unit = (peak_rec.unit or "").strip()
        lines.append(
            f"{metric}: {lo:g}->{hi:g}{unit}, peak {hi:g} at {_hm(peak_rec.ts)}{_tag(peak_ref)}"
        )
    return "; ".join(lines)


def _logs(results: list[Any], refs: list[str]) -> str:
    groups: dict[str, list[tuple[Any, str]]] = defaultdict(list)
    for rec, ref in _pairs(results, refs):
        groups[rec.message].append((rec, ref))
    parts = []
    for message, items in list(groups.items())[:_MAX_LOG_GROUPS]:
        rec, ref = items[0]
        count = f" ×{len(items)}" if len(items) > 1 else ""
        parts.append(f'{rec.level}{count}: "{message}"{_tag(ref)}')
    return f"{len(results)} logs — " + "; ".join(parts)


def _deploys(results: list[Any], refs: list[str]) -> str:
    return "; ".join(
        f"{rec.service} {rec.deploy_id} v{rec.version} at {_hm(rec.ts)} ({rec.note}){_tag(ref)}"
        for rec, ref in _pairs(results, refs)[:_MAX_ITEMS]
    )


def _deps(results: list[Any], refs: list[str]) -> str:
    return "; ".join(
        f"{rec.from_service}->{rec.to_service}"
        f"{' (critical)' if getattr(rec, 'critical', False) else ''}{_tag(ref)}"
        for rec, ref in _pairs(results, refs)[:_MAX_ITEMS]
    )


def _alerts(results: list[Any], refs: list[str]) -> str:
    triggers = [r for r in results if getattr(r, "is_trigger", False)]
    shown = (triggers or results)[:_MAX_ITEMS]
    return f"{len(results)} alerts — " + "; ".join(
        f"{r.service}: {r.signal or r.title}" for r in shown
    )


def _incident(results: list[Any], refs: list[str]) -> str:
    r = results[0]
    return f"{r.short_description} (priority {r.priority}, {r.category})"


def _docs(results: list[Any], refs: list[str]) -> str:
    return "; ".join(f"{r.doc_id}: {r.title}" for r in results[:_MAX_ITEMS])


_SUMMARIZERS = {
    "get_metrics": _metrics,
    "query_logs": _logs,
    "get_deployments": _deploys,
    "get_service_dependencies": _deps,
    "get_correlated_alerts": _alerts,
    "get_incident": _incident,
    "search_runbooks": _docs,
    "search_past_incidents": _docs,
}


def summarize(tool: str, results: list[Any], refs: list[str]) -> str:
    """A compact `signal [ref]` view of a tool's results. Empty -> "no results"; error -> count."""
    if not results:
        return "no results"
    summarizer = _SUMMARIZERS.get(tool)
    if summarizer is None:
        return f"{len(results)} result(s)"
    try:
        return summarizer(results, refs)
    except Exception:  # noqa: BLE001 — a summary must never break the diagnosis loop
        return f"{len(results)} result(s)"
