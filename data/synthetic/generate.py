"""Generate RetailEase telemetry from the answer key, calibrated by the RCAEval profile.

This is the deterministic 2b generator. It reads three inputs — the topology and scenario
answer key (2a) and the empirical signal profile (RCAEval) — and emits the telemetry the
Phase 3 tools will query:

    data/synthetic/logs.jsonl          (log rows; query_logs)
    data/synthetic/metrics.json        (metric series; get_metrics)
    data/synthetic/deployments.json    (deploys; get_deployments)
    data/synthetic/dependencies.json   (edges; get_service_dependencies)

Design contract:
  * SIGNAL is authored. Every `expected_evidence` ref in the answer key resolves to a real row
    here — that's asserted by tests/test_telemetry.py.
  * NOISE is calibrated. Its density comes from the RCAEval profile, not from guesses: only a
    small fraction of metrics deviate (affected_metric_fraction), symptoms reach only part of the
    fleet (blast_radius_fraction), and the log noise floor matches the ambient error rate.
  * SEVERITY is checked, not invented. Each scenario's authored severity is validated against a
    blast-radius × path-criticality estimate; a mismatch is surfaced, not silently accepted.
  * AMBIENT sub-threshold events are the same failure modes at low intensity — the coherent noise
    that gives non-incident negatives and a realistic severity floor.

Everything is deterministic (seeded by content hash — no wall-clock, no RNG), so the corpus is
regenerable and the evals reproducible.

Run:  python data/synthetic/generate.py
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

SYN_DIR = Path(__file__).resolve().parent
REPO_ROOT = SYN_DIR.parents[1]
ANSWER_KEY = REPO_ROOT / "data" / "answer_key"
PROFILE_PATH = REPO_ROOT / "data" / "profiles" / "rcaeval_profile.json"

WINDOW_MIN = 30          # telemetry window is occurred_at ± 30 min...
STEP_MIN = 5             # ...sampled every 5 min (matches topology.metric_sample_interval_minutes).
NOISE_LOG_SCALE = 0.02   # scale RCAEval's ~335 lines/min/svc down to a tractable demo volume,
                         # preserving the ambient_error_fraction ratio (documented, not silent).

# ---------------------------------------------------------------------------------------------
# Metric catalog — the metrics each entity emits. Referenced metrics (named in evidence) MUST be
# present; the rest are the quiet majority that make the affected fraction realistically sparse.
# baseline/deviated are steady-state vs during-fault values; direction documents the shift.
# ---------------------------------------------------------------------------------------------
METRIC_DEFS: dict[str, dict[str, Any]] = {
    "http_5xx_rate":         {"unit": "ratio", "baseline": 0.002, "deviated": 0.085},
    "p95_latency_ms":        {"unit": "ms",    "baseline": 120.0, "deviated": 1800.0},
    "request_rate":          {"unit": "rps",   "baseline": 55.0,  "deviated": 55.0},  # flat=noise
    "cpu_pct":               {"unit": "pct",   "baseline": 32.0,  "deviated": 32.0},  # flat=noise
    "reservation_error_rate":{"unit": "ratio", "baseline": 0.001, "deviated": 0.06},
    "restart_count":         {"unit": "count", "baseline": 0.0,   "deviated": 6.0},
    "ru_throttled_rate":     {"unit": "ratio", "baseline": 0.0,   "deviated": 0.22},
    "used_ru_pct":           {"unit": "pct",   "baseline": 45.0,  "deviated": 98.0},
    "active_message_count":  {"unit": "count", "baseline": 25.0,  "deviated": 5200.0},
    "incoming_rate":         {"unit": "rps",   "baseline": 30.0,  "deviated": 30.0},  # flat=noise
    "used_memory_pct":       {"unit": "pct",   "baseline": 58.0,  "deviated": 97.0},
    "evicted_keys_rate":     {"unit": "rps",   "baseline": 0.0,   "deviated": 3100.0},
    "hit_rate":              {"unit": "ratio", "baseline": 0.95,  "deviated": 0.62},
    "msg_processed_rate":    {"unit": "rps",   "baseline": 28.0,  "deviated": 0.0},
}

ENTITY_METRICS: dict[str, list[str]] = {
    "checkout-api":        ["http_5xx_rate", "p95_latency_ms", "request_rate", "cpu_pct"],
    "payment-api":         ["p95_latency_ms", "http_5xx_rate", "request_rate", "cpu_pct"],
    "inventory-api":       ["p95_latency_ms", "reservation_error_rate", "request_rate", "cpu_pct"],
    "catalog-api":         ["p95_latency_ms", "request_rate", "cpu_pct"],
    "notification-worker": ["restart_count", "msg_processed_rate", "cpu_pct"],
    "cosmos-db":           ["ru_throttled_rate", "used_ru_pct"],
    "service-bus":         ["active_message_count", "incoming_rate"],
    "redis-cache":         ["used_memory_pct", "evicted_keys_rate", "hit_rate"],
}

# Log messages for each authored event id (evidence `logs:<svc>:<event_id>`).
LOG_EVENTS: dict[str, dict[str, str]] = {
    "evt-001-01": {"service": "payment-api", "level": "error",
                   "message": "Cosmos connection pool exhausted; payment authorization timed out"},
    "evt-001-02": {"service": "checkout-api", "level": "error",
                   "message": "503 from payment-api authorize call; returning checkout failure"},
    "evt-002-01": {"service": "inventory-api", "level": "error",
                   "message": "429 TooManyRequests from cosmos-db on stock read"},
    "evt-002-02": {"service": "catalog-api", "level": "error",
                   "message": "429 TooManyRequests from cosmos-db on catalog read"},
    "evt-003-01": {"service": "notification-worker", "level": "error",
                   "message": "Unhandled deserialization exception; restarting (crash loop)"},
    "evt-004-01": {"service": "checkout-api", "level": "error",
                   "message": "500 InternalServerError on /checkout"},
    "evt-004-02": {"service": "payment-api", "level": "error",
                   "message": "PaymentGatewayTimeout calling external payment-gateway"},
    "evt-005-01": {"service": "checkout-api", "level": "warn",
                   "message": "session not found in cache; cold-loading from datastore"},
    "evt-006-01": {"service": "inventory-api", "level": "error",
                   "message": "StockReservationConflict; oversell detected on SKU"},
    "evt-006-02": {"service": "checkout-api", "level": "error",
                   "message": "reserve failed: inventory conflict"},
}

# Deploys named in evidence (`deploys:<svc>:<deploy_id>`). ts is authored relative to the incident.
DEPLOYS: dict[str, dict[str, str]] = {
    "dep-20260512-01": {"service": "payment-api", "ts": "2026-05-12T14:00:00Z",
                        "version": "payment-api@2.4.1",
                        "note": "reduced Cosmos connection pool 100->10 (causal: inc-001)"},
    "dep-20260528-01": {"service": "catalog-api", "ts": "2026-05-28T09:00:00Z",
                        "version": "catalog-api@1.9.0",
                        "note": "catalog bulk-import job rollout (trigger: inc-002)"},
    "dep-20260610-01": {"service": "notification-worker", "ts": "2026-06-10T19:45:00Z",
                        "version": "notification-worker@3.1.0",
                        "note": "worker release with poison-message bug (causal: inc-003)"},
    "dep-20260628-01": {"service": "checkout-api", "ts": "2026-06-28T09:00:00Z",
                        "version": "checkout-api@5.7.2",
                        "note": "routine checkout release (RED HERRING: coincidental to inc-004)"},
    "dep-20260625-01": {"service": "inventory-api", "ts": "2026-06-25T16:00:00Z",
                        "version": "inventory-api@4.2.0",
                        "note": "dropped cache invalidation on stock writes (causal: inc-006)"},
}

# A few routine, unrelated deploys — deploy-feed noise so "recent deploy" is a hypothesis to test.
ROUTINE_DEPLOYS = [
    {"deploy_id": "dep-20260601-07", "service": "catalog-api", "ts": "2026-06-01T11:00:00Z",
     "version": "catalog-api@1.9.3", "note": "routine"},
    {"deploy_id": "dep-20260615-02", "service": "checkout-api", "ts": "2026-06-15T13:30:00Z",
     "version": "checkout-api@5.6.0", "note": "routine"},
    {"deploy_id": "dep-20260620-04", "service": "inventory-api", "ts": "2026-06-20T10:15:00Z",
     "version": "inventory-api@4.1.2", "note": "routine"},
]

# Ambient sub-threshold events — the SAME failure modes at low intensity. They stay below the
# incident threshold: coherent noise + non-incident negatives (the SEV4/"don't page" floor).
AMBIENT_EVENTS = [
    {"id": "amb-01", "service": "catalog-api", "ts": "2026-06-18T03:20:00Z", "level": "warn",
     "message": "429 TooManyRequests from cosmos-db (single, retried, served from cache)",
     "metric": ("cosmos-db", "ru_throttled_rate", 0.02)},
    {"id": "amb-02", "service": "notification-worker", "ts": "2026-06-19T22:05:00Z",
     "level": "warn", "message": "worker restarted once (transient)",
     "metric": ("notification-worker", "restart_count", 1.0)},
    {"id": "amb-03", "service": "redis-cache", "ts": "2026-06-21T07:45:00Z", "level": "info",
     "message": "brief eviction blip under load (recovered)",
     "metric": ("redis-cache", "evicted_keys_rate", 90.0)},
    {"id": "amb-04", "service": "payment-api", "ts": "2026-06-23T15:10:00Z", "level": "warn",
     "message": "single payment-gateway retry (recovered)",
     "metric": ("payment-api", "p95_latency_ms", 400.0)},
]


def _dt(iso: str | datetime) -> datetime:
    if isinstance(iso, datetime):  # YAML parses bare timestamps (occurred_at) straight to datetime
        return iso if iso.tzinfo else iso.replace(tzinfo=UTC)
    return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _rng(*keys: str) -> float:
    """Deterministic pseudo-random in [0,1) from a content hash — no wall-clock, no RNG state."""
    h = hashlib.sha256("|".join(keys).encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _jitter(base: float, *keys: str, spread: float = 0.05) -> float:
    return round(base * (1 + (_rng(*keys) - 0.5) * 2 * spread), 6)


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def parse_evidence(refs: list[str]) -> dict[str, list]:
    """Split an evidence list into per-source targets the generator must realize."""
    out: dict[str, list] = {"metrics": [], "logs": [], "deploys": [], "deps": []}
    for ref in refs:
        source, rest = ref.split(":", 1)
        if source == "metrics":
            svc, tail = rest.split(":", 1)
            metric, ts = tail.split("@", 1)
            out["metrics"].append((svc, metric, ts))
        elif source == "logs":
            svc, event_id = rest.rsplit(":", 1)
            out["logs"].append((svc, event_id))
        elif source == "deploys":
            svc, dep_id = rest.rsplit(":", 1)
            out["deploys"].append((svc, dep_id))
        elif source == "deps":
            out["deps"].append(rest)
    return out


def time_grid(center: datetime) -> list[datetime]:
    start = center - timedelta(minutes=WINDOW_MIN)
    n = (2 * WINDOW_MIN) // STEP_MIN
    return [start + timedelta(minutes=STEP_MIN * i) for i in range(n + 1)]


def build_metrics(scenarios: list[dict]) -> tuple[list[dict], set[str]]:
    """Per window emit every entity's full metric catalog; deviate only referenced (svc,metric)."""
    series: list[dict] = []
    resolved: set[str] = set()
    for s in scenarios:
        ev = parse_evidence(s["expected_evidence"])
        center = _dt(s["occurred_at"])
        grid = time_grid(center)
        # (svc, metric) -> earliest deviation ts; onset elevates one sample earlier for a ramp.
        dev_ts: dict[tuple[str, str], datetime] = {}
        for svc, metric, ts in ev["metrics"]:
            key = (svc, metric)
            dev_ts[key] = min(dev_ts.get(key, _dt(ts)), _dt(ts))
        for entity, metrics in ENTITY_METRICS.items():
            for metric in metrics:
                d = METRIC_DEFS[metric]
                onset = dev_ts.get((entity, metric))
                samples = [
                    {"ts": _iso(g), "value": _jitter(
                        d["deviated"] if (onset and g >= onset - timedelta(minutes=STEP_MIN))
                        else d["baseline"], s["id"], entity, metric, _iso(g))}
                    for g in grid
                ]
                series.append({"incident_id": s["id"], "service": entity, "metric": metric,
                               "unit": d["unit"], "samples": samples})
        # Every referenced metric ref is now realized (its ts lies on the grid and is elevated).
        for svc, metric, ts in ev["metrics"]:
            resolved.add(f"metrics:{svc}:{metric}@{ts}")
    return series, resolved


def build_logs(scenarios: list[dict], profile: dict) -> tuple[list[dict], set[str]]:
    """Authored incident error events + a calibrated ambient noise floor + ambient sub-threshold."""
    rows: list[dict] = []
    resolved: set[str] = set()
    per_cat = profile.get("per_category", {})
    for s in scenarios:
        ev = parse_evidence(s["expected_evidence"])
        center = _dt(s["occurred_at"])
        cat = per_cat.get(s["category"], {})
        err_frac = cat.get("ambient_error_fraction") or 0.065
        rate = cat.get("log_lines_per_min_per_service") or 320.0
        # 1) authored signal — the exact evidence rows.
        for svc, event_id in ev["logs"]:
            spec = LOG_EVENTS[event_id]
            ts = _iso(center + timedelta(seconds=3 + int(_rng(event_id) * 90)))
            rows.append({"event_id": event_id, "ts": ts, "service": spec["service"],
                         "level": spec["level"], "message": spec["message"],
                         "incident_id": s["id"]})
            resolved.add(f"logs:{svc}:{event_id}")
        # 2) calibrated noise floor — scaled volume, real ambient error fraction.
        n_noise = max(1, int(rate * (2 * WINDOW_MIN) * NOISE_LOG_SCALE))
        for svc in _SERVICES:
            for i in range(n_noise):
                seed = f"{s['id']}|{svc}|{i}"
                off = int(_rng(seed, "t") * 2 * WINDOW_MIN * 60)
                is_err = _rng(seed, "e") < err_frac
                rows.append({
                    "event_id": f"noise-{s['id']}-{svc}-{i}",
                    "ts": _iso(center - timedelta(minutes=WINDOW_MIN) + timedelta(seconds=off)),
                    "service": svc, "level": "error" if is_err else "info",
                    "message": ("upstream call failed; retrying" if is_err
                                else f"GET {svc} 200 {int(20 + _rng(seed,'l')*180)}ms"),
                    "incident_id": None})
    # 3) ambient sub-threshold events (non-incident negatives).
    for a in AMBIENT_EVENTS:
        rows.append({"event_id": a["id"], "ts": a["ts"], "service": a["service"],
                     "level": a["level"], "message": a["message"],
                     "incident_id": None, "label": "non_incident"})
    rows.sort(key=lambda r: r["ts"])
    return rows, resolved


def build_deploys(scenarios: list[dict]) -> tuple[list[dict], set[str]]:
    rows: list[dict] = []
    resolved: set[str] = set()
    referenced: set[str] = set()
    for s in scenarios:
        for svc, dep_id in parse_evidence(s["expected_evidence"])["deploys"]:
            referenced.add(dep_id)
            resolved.add(f"deploys:{svc}:{dep_id}")
    for dep_id, spec in DEPLOYS.items():
        rows.append({"deploy_id": dep_id, **spec})
    rows.extend(ROUTINE_DEPLOYS)
    rows.sort(key=lambda r: r["ts"])
    missing = referenced - set(DEPLOYS)
    if missing:
        raise ValueError(f"evidence references undefined deploys: {missing}")
    return rows, resolved


def build_deps(topology: dict) -> tuple[list[dict], set[str]]:
    rows, resolved = [], set()
    for d in topology["dependencies"]:
        rows.append(d)
        resolved.add(f"deps:{d['from']}->{d['to']}")
    return rows, resolved


def severity_check(scenarios: list[dict]) -> list[str]:
    """Estimate severity from blast radius × whether it reaches the customer edge; warn on drift."""
    warnings: list[str] = []
    n_services = len(_SERVICES)
    order = {"SEV4": 1, "SEV3": 2, "SEV2": 3, "SEV1": 4}
    for s in scenarios:
        chain_services = [e for e in s["impacted_chain"] if e in _SERVICES]
        blast = len(chain_services) / n_services
        reaches_edge = "checkout-api" in s["impacted_chain"]
        if reaches_edge and blast >= 0.4:
            est = "SEV1"
        elif reaches_edge:
            est = "SEV2"
        elif blast >= 0.2:
            est = "SEV3"
        else:
            est = "SEV4"
        if abs(order[est] - order[s["severity"]]) > 1:
            warnings.append(
                f"{s['id']}: authored {s['severity']} but blast/criticality suggests ~{est}")
    return warnings


def _dump(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


_SERVICES: set[str] = set()


def main() -> None:
    global _SERVICES
    topology = load_yaml(ANSWER_KEY / "topology.yaml")
    scenarios = load_yaml(ANSWER_KEY / "scenarios.yaml")["scenarios"]
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    _SERVICES = {s["id"] for s in topology["services"]}
    SYN_DIR.mkdir(parents=True, exist_ok=True)

    metrics, m_res = build_metrics(scenarios)
    logs, l_res = build_logs(scenarios, profile)
    deploys, dep_res = build_deploys(scenarios)
    deps, deps_res = build_deps(topology)

    _dump(SYN_DIR / "metrics.json", {"series": metrics})
    (SYN_DIR / "logs.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in logs), encoding="utf-8")
    _dump(SYN_DIR / "deployments.json", {"deployments": deploys})
    _dump(SYN_DIR / "dependencies.json", {"edges": deps})

    # Report ref-resolution + severity consistency (2e will hard-gate these).
    all_resolved = m_res | l_res | dep_res | deps_res
    required = {ref for s in scenarios for ref in s["expected_evidence"]}
    unresolved = required - all_resolved
    print(f"metrics: {len(metrics)} series | logs: {len(logs)} rows | "
          f"deploys: {len(deploys)} | edges: {len(deps)}")
    print(f"evidence refs required={len(required)} resolved={len(required & all_resolved)}")
    if unresolved:
        print(f"  !! UNRESOLVED: {sorted(unresolved)}")
    for w in severity_check(scenarios):
        print(f"  severity-check: {w}")


if __name__ == "__main__":
    main()
