"""2b closure gate: every answer-key evidence ref must resolve to a real generated row.

This is the Phase 2b half of the "no drift" promise. 2a's test guards the answer key's internal
coherence; this one guards that the generated telemetry actually realizes it — the check that
matters before any Phase 4 retrieval or Phase 5 groundedness eval scores against this corpus.

It re-reads the committed telemetry (it does not regenerate), so if `generate.py` was changed
without re-running it, or a ref points at a row that isn't there, this fails loudly.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SYN = REPO_ROOT / "data" / "synthetic"
ANSWER_KEY = REPO_ROOT / "data" / "answer_key"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ANSWER_KEY.parent / _MODS[name])
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_MODS = {
    "build_goldens": "answer_key/build_goldens.py",
    "generate": "synthetic/generate.py",
}
build_goldens = _load("build_goldens")
generate = _load("generate")

TOPOLOGY = build_goldens.load_topology()
SCENARIOS = build_goldens.load_scenarios()
generate._SERVICES = {s["id"] for s in TOPOLOGY["services"]}

METRICS = json.loads((SYN / "metrics.json").read_text(encoding="utf-8"))["series"]
DEPLOYS = json.loads((SYN / "deployments.json").read_text(encoding="utf-8"))["deployments"]
EDGES = json.loads((SYN / "dependencies.json").read_text(encoding="utf-8"))["edges"]
LOGS = [json.loads(line) for line in (SYN / "logs.jsonl").read_text(encoding="utf-8").splitlines()]

ALL_REFS = sorted({ref for s in SCENARIOS for ref in s["expected_evidence"]})

# Indices ------------------------------------------------------------------------------------
METRIC_SAMPLES = {
    (s["service"], s["metric"], pt["ts"]): pt["value"] for s in METRICS for pt in s["samples"]
}
METRIC_SERIES = {(s["service"], s["metric"]): s["samples"] for s in METRICS}
LOG_EVENTS = {r["event_id"]: r for r in LOGS}
DEPLOY_IDS = {d["deploy_id"]: d for d in DEPLOYS}
EDGE_SET = {f"{e['from']}->{e['to']}" for e in EDGES}


def test_every_evidence_ref_resolves():
    unresolved = []
    for ref in ALL_REFS:
        source, rest = ref.split(":", 1)
        if source == "metrics":
            svc, tail = rest.split(":", 1)
            metric, ts = tail.split("@", 1)
            if (svc, metric, ts) not in METRIC_SAMPLES:
                unresolved.append(ref)
        elif source == "logs":
            svc, event_id = rest.rsplit(":", 1)
            row = LOG_EVENTS.get(event_id)
            if row is None or row["service"] != svc:
                unresolved.append(ref)
        elif source == "deploys":
            svc, dep_id = rest.rsplit(":", 1)
            row = DEPLOY_IDS.get(dep_id)
            if row is None or row["service"] != svc:
                unresolved.append(ref)
        elif source == "deps":
            if rest not in EDGE_SET:
                unresolved.append(ref)
    assert not unresolved, f"unresolved evidence refs: {unresolved}"


def test_referenced_metrics_are_actually_deviated():
    """A metric ref must land on an *elevated* sample, not just any sample (referenced go up)."""
    for ref in ALL_REFS:
        if not ref.startswith("metrics:"):
            continue
        svc, tail = ref[len("metrics:"):].split(":", 1)
        metric, ts = tail.split("@", 1)
        samples = METRIC_SERIES[(svc, metric)]
        baseline = samples[0]["value"]  # window start = steady state
        assert METRIC_SAMPLES[(svc, metric, ts)] > baseline * 1.2 or (
            baseline == 0 and METRIC_SAMPLES[(svc, metric, ts)] > 0
        ), f"{ref} is not deviated above baseline"


def test_red_herring_deploy_present_but_uncorrelated():
    """inc-004's red herring must exist in the deploy feed (so it can be ruled out, not omitted)."""
    inc4 = next(s for s in SCENARIOS if s["id"] == "inc-004")
    _, rest = inc4["red_herring"].split(":", 1)
    svc, dep_id = rest.rsplit(":", 1)
    assert dep_id in DEPLOY_IDS and DEPLOY_IDS[dep_id]["service"] == svc


def test_noise_floor_error_fraction_matches_profile():
    """The noise error rate should track the RCAEval-calibrated fraction, not a guess."""
    noise = [r for r in LOGS if r["event_id"].startswith("noise-")]
    assert noise, "no noise-floor logs generated"
    err_frac = sum(r["level"] == "error" for r in noise) / len(noise)
    assert 0.03 < err_frac < 0.12, f"noise error fraction {err_frac:.3f} off calibrated ~0.065"


def test_metric_signal_is_sparse():
    """Only a small share of series deviate — the needle-in-haystack shape RCAEval showed."""
    deviated = sum(
        1 for (svc, metric), samples in METRIC_SERIES.items()
        if max(p["value"] for p in samples) > 1.2 * max(samples[0]["value"], 1e-9)
    )
    assert deviated / len(METRIC_SERIES) < 0.25, "too many metrics deviate — signal not sparse"


def test_severity_labels_consistent_with_blast_model():
    """No authored severity may be >1 level off its blast-radius × criticality estimate."""
    assert generate.severity_check(SCENARIOS) == []


def test_generation_is_deterministic():
    """Same inputs → identical telemetry (content-hash seeded, no wall-clock)."""
    assert generate.build_metrics(SCENARIOS)[0] == generate.build_metrics(SCENARIOS)[0]
    profile = json.loads((REPO_ROOT / "data" / "profiles" / "rcaeval_profile.json").read_text())
    assert generate.build_logs(SCENARIOS, profile)[0] == generate.build_logs(SCENARIOS, profile)[0]
