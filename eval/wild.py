"""RCAEval wild-slice generalization probe (Stage 4d).

Runs the diagnosis core against the held-out Online Boutique RCAEval slice — real third-party
telemetry it was never tuned on. Each RE1 fault *case* is a directory `<service>_<fault>/<n>/`
containing `data.csv` (metric columns `<service>_<metric>`, a `time` column in unix seconds) and
`inject_time.txt`; the parent directory names the injected **root service** (the ground truth).

Each case becomes an OpsPilot incident whose metrics the *same* tools query — no diagnosis-core
changes. We score whether the agent names the injected root service (`rca_correctness`) on telemetry
it never saw. RE1 is metrics-only (no logs/deploys), so this probes metric-anomaly RCA
generalization; a synthetic dependency star lets the agent discover which services exist to query,
and retrieval is suppressed so no RetailEase knowledge leaks in.

Raw RCAEval data is gitignored — drop `RE1-OB.zip` into `data/.rcaeval_cache/`. A tiny committed
fixture (`tests/fixtures/wild_ob/`) exercises the harness without it.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE = REPO_ROOT / "data" / ".rcaeval_cache" / "RE1-OB"

_FAULT_SUFFIXES = ("cpu", "mem", "disk", "delay", "loss", "socket")
_ENTRY = "frontend-lb"      # synthetic entry node: the symptom surfaces here, root is downstream
_MAX_SAMPLES = 40           # downsample each series so the in-memory corpus stays tractable


@dataclass
class WildCase:
    incident_id: str
    root_service: str
    fault_type: str
    inject_ts: datetime
    services: list[str] = field(default_factory=list)
    metric_series: list[dict[str, Any]] = field(default_factory=list)


def _service_of(column: str) -> str | None:
    """Owning service = token before the first underscore; drop node-exporter (IP-prefixed) cols."""
    head = column.split("_", 1)[0]
    if not head or head[0].isdigit():
        return None
    return head


def _root_and_fault(dir_name: str) -> tuple[str, str]:
    for fault in _FAULT_SUFFIXES:
        if dir_name.endswith("_" + fault):
            return dir_name[: -(len(fault) + 1)], fault
    service, _, fault = dir_name.rpartition("_")
    return (service or dir_name), fault


def _downsample(rows: list[int]) -> list[int]:
    """Indices to keep so a long series collapses to <= _MAX_SAMPLES evenly-spaced points."""
    n = len(rows)
    if n <= _MAX_SAMPLES:
        return list(range(n))
    step = (n + _MAX_SAMPLES - 1) // _MAX_SAMPLES
    return list(range(0, n, step))


def load_case(case_dir: Path, incident_id: str) -> WildCase | None:
    """Parse one RE1 case dir (`.../<service>_<fault>/<n>/`) into a WildCase, or None if bad."""
    inject_file, data_file = case_dir / "inject_time.txt", case_dir / "data.csv"
    if not (inject_file.exists() and data_file.exists()):
        return None
    try:
        inject_ts = datetime.fromtimestamp(int(inject_file.read_text().strip()), tz=UTC)
    except ValueError:
        return None
    root_service, fault = _root_and_fault(case_dir.parent.name)

    with data_file.open(newline="") as fh:
        reader = csv.DictReader(fh)
        columns = reader.fieldnames or []
        rows = list(reader)
    if "time" not in columns or not rows:
        return None
    keep = _downsample(rows)
    times = [datetime.fromtimestamp(float(rows[i]["time"]), tz=UTC).isoformat() for i in keep]

    series: list[dict[str, Any]] = []
    services: set[str] = set()
    for col in columns:
        service = _service_of(col) if col != "time" else None
        if service is None:
            continue
        metric = col[len(service) + 1:] or col
        samples = []
        for idx, ts in zip(keep, times, strict=True):
            try:
                samples.append({"ts": ts, "value": float(rows[idx][col])})
            except (ValueError, TypeError):
                continue
        if not samples:
            continue
        services.add(service)
        series.append({"incident_id": incident_id, "service": service,
                       "metric": metric, "unit": "", "samples": samples})

    if root_service not in services:  # ground truth must resolve against the telemetry
        return None
    return WildCase(incident_id=incident_id, root_service=root_service, fault_type=fault,
                    inject_ts=inject_ts, services=sorted(services), metric_series=series)


def load_cases(
    cache_dir: Path | str = DEFAULT_CACHE, *, limit: int | None = None, per_group: int = 1
) -> list[WildCase]:
    """Discover RE1 cases (nesting-agnostic) as a DIVERSE slice: up to `per_group` cases from each
    `<service>_<fault>` group, so the slice spans services and fault types rather than clustering on
    the first directory. Deterministic order; `limit` caps the total."""
    root = Path(cache_dir)
    by_group: dict[Path, list[Path]] = {}
    for inject in root.rglob("inject_time.txt"):
        case_dir = inject.parent
        by_group.setdefault(case_dir.parent, []).append(case_dir)

    cases: list[WildCase] = []
    for group in sorted(by_group):
        for case_dir in sorted(by_group[group])[:per_group]:
            label = f"{case_dir.parent.name}-{case_dir.name}"
            case = load_case(case_dir, incident_id=f"wild-{label}")
            if case is not None:
                cases.append(case)
            if limit is not None and len(cases) >= limit:
                return cases
    return cases


class _NoRetriever:
    """Retrieval suppressed for the wild probe: an OB incident must not pull RetailEase
    runbooks/postmortems, or the "never saw this" generalization claim would be false."""

    backend_name = "none"

    @property
    def docs(self) -> list[Any]:
        return []

    def search(self, query: str, k: int = 5, kinds: Any = None, services: Any = None) -> list[Any]:
        return []


def _incident_of(case: WildCase) -> dict[str, Any]:
    return {
        "number": case.incident_id,
        "incident_id": case.incident_id,
        "short_description": f"{_ENTRY} degraded — {case.fault_type} fault (Online Boutique)",
        "category": "wild",
        "priority": "3",  # SEV3: metrics-only can satisfy the sufficiency gate (>=1 class)
        "impact": "3",
        "urgency": "3",
        "opened_at": case.inject_ts.isoformat(),
        "state": "open",
        "made_sla": True,
        "reassignment_count": 0,
        "is_known_error": False,
    }


def _alert_of(case: WildCase) -> dict[str, Any]:
    return {
        "alert_id": f"{case.incident_id}-a1",
        "incident_id": case.incident_id,
        "service": _ENTRY,  # the symptom surfaces at the entry; the root is downstream
        "severity": "SEV3",
        "role": "trigger",
        "is_trigger": True,
        "signal": f"{_ENTRY} error rate elevated",
        "title": f"{_ENTRY} degraded",
        "fired_at": case.inject_ts.isoformat(),
        "dedup_key": f"{case.incident_id}-dedup",
    }


def _edges_of(case: WildCase) -> list[dict[str, Any]]:
    # A dependency star from the synthetic entry to every observed service, so the agent can
    # DISCOVER which services exist to query (RE1 ships no topology). Not the true OB graph — it
    # gives the agent the service list, not the answer.
    return [{"from": _ENTRY, "to": svc, "kind": "calls", "critical": False}
            for svc in case.services]


def build_wild_repository(cases: list[WildCase]):
    """One in-memory Repository for the given cases. Use ONE case per repo in the eval, since
    get_metrics filters by service (not incident) and would otherwise mix cases' telemetry."""
    from opspilot.data.repository import Repository

    incidents = [_incident_of(c) for c in cases]
    alerts = [_alert_of(c) for c in cases]
    metrics = [s for c in cases for s in c.metric_series]
    edges = [e for c in cases for e in _edges_of(c)]
    return Repository.from_records(incidents=incidents, alerts=alerts, metrics=metrics, edges=edges)


def _implicated_service(state: dict[str, Any]) -> str | None:
    """The service the hypothesis blames, read from its structured citations (never from prose).

    Prefer a metric/log citation (the root's own evidence). For a dependency citation, use the
    TO-side: the wild corpus's edges are a star from the synthetic entry, so the from-side is always
    the meaningless entry and the to-side is the real service the agent points at.
    """
    citations = list(state.get("hypothesis").citations) if state.get("hypothesis") else []
    for citation in citations:
        parts = citation.ref.split(":")
        if parts[0] in ("metrics", "logs", "deploys") and len(parts) > 1:
            return parts[1]
    for citation in citations:
        parts = citation.ref.split(":")
        if parts[0] == "deps" and len(parts) > 1 and "->" in parts[1]:
            return parts[1].split("->")[1]
    return None


def evaluate_wild(
    implementation: str = "deterministic",
    *,
    cache_dir: Path | str = DEFAULT_CACHE,
    model: Any = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Score RCA generalization on the held-out OB slice: fraction of cases where the agent names
    the injected root service. Returns a note (rca None) if the raw data is absent."""
    from opspilot.diagnosis.planner import build_planner
    from opspilot.graph import _initial_state, build_graph
    from opspilot.tools.service import ToolService
    from opspilot.triage import build_triager

    cases = load_cases(cache_dir, limit=limit)
    if not cases:
        return {"implementation": implementation, "n_cases": 0, "rca_correctness": None,
                "note": f"no RE1 cases under {cache_dir} — download RE1-OB.zip into the cache"}

    app = build_graph()
    per_case, correct = [], 0
    for case in cases:
        svc = ToolService(repo=build_wild_repository([case]), retriever_factory=_NoRetriever)
        config = {"configurable": {
            "tool_service": svc,
            "planner": build_planner(implementation, model=model),
            "triager": build_triager(implementation, model=model),
        }}
        state = app.invoke(
            _initial_state({"incident_id": case.incident_id, "summary": f"{_ENTRY} degraded"}),
            config=config)
        implicated = _implicated_service(state)
        ok = implicated == case.root_service
        correct += int(ok)
        per_case.append({"incident": case.incident_id, "root": case.root_service,
                         "implicated": implicated, "correct": ok})

    return {
        "implementation": implementation,
        "n_cases": len(cases),
        "rca_correctness": round(correct / len(cases), 4),
        "per_case": per_case,
    }
