"""get_metrics — metric samples for an entity (service or infra), optional metric + window.

Evidence-bearing: each sample yields `metrics:<service>:<metric>@<ts>`. The ref reuses the raw
sample timestamp string so it matches the answer key exactly (no reformatting drift).
"""

from __future__ import annotations

from opspilot.data.repository import Repository
from opspilot.tools.contracts import GetMetricsRequest, MetricSample, ToolResult, to_utc
from opspilot.tools.errors import run_tool


def get_metrics(repo: Repository, **kwargs) -> ToolResult[MetricSample]:
    def logic(req: GetMetricsRequest) -> tuple[list[MetricSample], list[str]]:
        start = to_utc(req.start_time) if req.start_time else None
        end = to_utc(req.end_time) if req.end_time else None
        recs: list[MetricSample] = []
        refs: list[str] = []
        for series in repo.metric_series():
            if series.get("service") != req.service:
                continue
            if req.metric and series.get("metric") != req.metric:
                continue
            unit = series.get("unit", "")
            for sample in series.get("samples", []):
                raw_ts = sample["ts"]  # keep the exact string for the ref
                try:
                    rec = MetricSample(service=series["service"], metric=series["metric"],
                                       ts=raw_ts, value=sample["value"], unit=unit)
                except Exception:  # noqa: BLE001 — skip malformed samples
                    continue
                t = to_utc(rec.ts)
                if (start and t < start) or (end and t > end):
                    continue
                recs.append(rec)
                refs.append(f"metrics:{rec.service}:{rec.metric}@{raw_ts}")
        order = sorted(range(len(recs)), key=lambda i: (to_utc(recs[i].ts), recs[i].metric))
        return [recs[i] for i in order], [refs[i] for i in order]

    return run_tool("get_metrics", GetMetricsRequest, logic, **kwargs)
