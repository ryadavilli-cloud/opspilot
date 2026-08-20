"""2b closure gate: every answer-key evidence ref must resolve to a real generated row.

This is the generated half of the "no drift" promise. `test_answer_key.py` guards the answer key's
internal coherence; this one guards that the generated telemetry actually realizes it, which is the
check that matters before any retrieval or groundedness evaluation scores against this corpus.

It re-reads the committed telemetry (it does not regenerate), so if `generate.py` was changed
without re-running it, or a ref points at a row that isn't there, this fails loudly.
"""

from __future__ import annotations

import importlib.util
import json
import re
from datetime import timedelta
from pathlib import Path

import answer_key

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
    "generate": "synthetic/generate.py",
}
generate = _load("generate")

TOPOLOGY = answer_key.TOPOLOGY
SCENARIOS = answer_key.SCENARIOS
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
    """A metric ref must land on a sample that moved toward its own authored direction, not
    just any sample. Some referenced metrics rise (http_5xx_rate); some legitimately drop to
    signal (msg_processed_rate dropping to ~0 is exactly what "nothing is being consumed"
    looks like): a repaired series must move the way its own postmortem narrates, not just
    move away from baseline in either direction."""
    for ref in ALL_REFS:
        if not ref.startswith("metrics:"):
            continue
        svc, tail = ref[len("metrics:") :].split(":", 1)
        metric, ts = tail.split("@", 1)
        samples = METRIC_SERIES[(svc, metric)]
        baseline = samples[0]["value"]  # window start = steady state
        observed = METRIC_SAMPLES[(svc, metric, ts)]
        authored = generate.METRIC_DEFS[metric]
        assert authored["deviated"] != authored["baseline"], (
            f"{metric} has no authored direction (baseline == deviated) but is referenced"
        )
        if authored["deviated"] > authored["baseline"]:
            assert observed > baseline * 1.2 or (baseline == 0 and observed > 0), (
                f"{ref} should have risen above baseline but did not"
            )
        else:
            assert observed < baseline * 0.8 or baseline == 0, (
                f"{ref} should have dropped below baseline but did not"
            )


def test_causally_linked_log_pairs_stay_ordered():
    """Where the answer key asserts one authored log line causes another (inc-004, inc-006),
    the cause's timestamp must not land after the effect's: an inverted order reads as the
    effect happening for no reason, before its own cause exists."""
    for cause_id, effect_id in generate.CAUSE_BEFORE_EFFECT:
        assert LOG_EVENTS[cause_id]["ts"] <= LOG_EVENTS[effect_id]["ts"], (
            f"{cause_id} did not precede {effect_id}"
        )


def test_metric_onset_follows_its_causal_log():
    """inc-003/inc-007: the backlog metric's ramp must not start before the crash-loop log
    that causes it. The ramp onset sits STEP_MIN before the referenced sample's timestamp, so
    an onset earlier than the causal log means the metric moved before its own cause fired."""
    pairs = [
        ("inc-003", "evt-003-01", "service-bus", "active_message_count"),
        ("inc-007", "evt-007-01", "service-bus", "active_message_count"),
    ]
    for inc_id, cause_event, svc, metric in pairs:
        cause_ts = LOG_EVENTS[cause_event]["ts"]
        scenario = next(s for s in SCENARIOS if s["id"] == inc_id)
        ref = next(
            r for r in scenario["expected_evidence"] if r.startswith(f"metrics:{svc}:{metric}@")
        )
        ref_ts = ref.split("@", 1)[1]
        onset = generate._dt(ref_ts) - timedelta(minutes=generate.STEP_MIN)
        assert generate._iso(onset) >= cause_ts, (
            f"{inc_id}: {metric} onset {generate._iso(onset)} precedes cause log at {cause_ts}"
        )


def test_no_answer_leakage_in_tool_visible_fields():
    """Log messages and deploy notes are what the tools actually surface to a model. Neither
    may name another incident id or announce its own narrative role (red herring, causal,
    trigger): that hands the model the answer instead of requiring it to establish one."""
    leak = re.compile(r"inc-\d{3}|red herring|causal:|trigger:", re.IGNORECASE)
    for row in LOGS:
        assert not leak.search(row["message"]), (
            f"leak in log {row['event_id']!r}: {row['message']!r}"
        )
    for dep in DEPLOYS:
        assert not leak.search(dep["note"]), (
            f"leak in deploy note {dep['deploy_id']!r}: {dep['note']!r}"
        )


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
        1
        for (svc, metric), samples in METRIC_SERIES.items()
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
