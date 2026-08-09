"""Golden scenario records: the closure discipline extended to the evaluation-facing artifact.

`test_closure.py` proves the answer key's evidence resolves to real telemetry. The same rule
applies here, and for the same reason: a golden record naming evidence the corpus cannot produce
is a corpus gap, not a test failure to tolerate. Resolution is re-derived independently rather
than imported from the generators, matching how `test_closure.py` treats the answer key.

The shape assertions exist because the golden record is authored, not generated: nothing else
would catch a record that silently lost a part of the eight-part model, or that tagged an
incident with a scenario class the accepted five do not contain.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "data"
SYN = DATA / "synthetic"
KB = DATA / "kb"

GOLDEN = yaml.safe_load(
    (DATA / "answer_key" / "golden_scenarios.yaml").read_text(encoding="utf-8")
)["golden_scenarios"]
SCENARIOS = yaml.safe_load((DATA / "answer_key" / "scenarios.yaml").read_text(encoding="utf-8"))[
    "scenarios"
]

METRICS = json.loads((SYN / "metrics.json").read_text(encoding="utf-8"))["series"]
DEPLOYS = json.loads((SYN / "deployments.json").read_text(encoding="utf-8"))["deployments"]
EDGES = json.loads((SYN / "dependencies.json").read_text(encoding="utf-8"))["edges"]
LOGS = [json.loads(x) for x in (SYN / "logs.jsonl").read_text(encoding="utf-8").splitlines()]

METRIC_SAMPLES = {(s["service"], s["metric"], p["ts"]) for s in METRICS for p in s["samples"]}
LOG_BY_EVENT = {r["event_id"]: r for r in LOGS}
DEPLOY_BY_ID = {d["deploy_id"]: d for d in DEPLOYS}
EDGE_SET = {f"{e['from']}->{e['to']}" for e in EDGES}

# The five accepted scenario classes (evaluation.md section 4 / NFR-29). The benign or transient
# class is represented by the non-incident fixture and never tags a golden record, so it is not
# a legal value here.
ACCEPTED_CLASSES = {
    "clear_single_cause",
    "competing_or_ambiguous_hypotheses",
    "multiple_contributing_failures",
    "sparse_or_unavailable_evidence",
}
ACCEPTED_OUTCOMES = {"complete", "partial", "inconclusive"}
REQUIRED_PARTS = {
    "incident",
    "classes",
    "expected_cause",
    "acceptable_alternatives",
    "required_evidence",
    "contradicting_or_unavailable",
    "expected_outcome_shape",
    "required_behavior",
}


def _kb_doc_exists(ref: str) -> bool:
    ns, ident = ref.split(":", 1)
    if ns == "runbook":
        return (KB / "runbooks" / f"{ident}.md").exists()
    if ns == "architecture":
        return (KB / "architecture" / f"{ident}.md").exists()
    if ns == "postmortem":
        return bool(sorted((KB / "postmortems").glob(f"{ident}-*.md")))
    return False


def _resolves(ref: str) -> bool:
    src, rest = ref.split(":", 1)
    if src == "metrics":
        svc, tail = rest.split(":", 1)
        metric, ts = tail.split("@", 1)
        return (svc, metric, ts) in METRIC_SAMPLES
    if src == "logs":
        svc, event_id = rest.rsplit(":", 1)
        return event_id in LOG_BY_EVENT and LOG_BY_EVENT[event_id]["service"] == svc
    if src == "deploys":
        svc, deploy_id = rest.rsplit(":", 1)
        return deploy_id in DEPLOY_BY_ID and DEPLOY_BY_ID[deploy_id]["service"] == svc
    if src == "deps":
        return rest in EDGE_SET
    if src in ("runbook", "architecture", "postmortem"):
        return _kb_doc_exists(ref)
    return False


def _all_references(record: dict) -> list[str]:
    refs: list[str] = []
    for group in record["required_evidence"]:
        refs += group.get("any_of", []) + group.get("all_of", [])
    refs += [w["reference"] for w in record["contradicting_or_unavailable"]["weakens_candidate"]]
    return refs


# --- closure: the property this file exists for -----------------------------------------------
def test_every_golden_reference_resolves_in_the_corpus():
    unresolved = [
        (record["incident"], ref)
        for record in GOLDEN
        for ref in _all_references(record)
        if not _resolves(ref)
    ]
    assert not unresolved, (
        f"golden records name evidence the corpus cannot produce: {unresolved}. "
        "This is a corpus gap, not a test to relax."
    )


def test_deliberately_absent_evidence_is_prose_never_a_reference():
    # Part 6 carries two different ideas. Something the corpus deliberately does not contain
    # cannot be a reference, because a reference to it would not resolve; recording it as one
    # would either break closure or, worse, quietly pass by naming something that does exist.
    for record in GOLDEN:
        for entry in record["contradicting_or_unavailable"]["deliberately_absent"]:
            assert isinstance(entry, str), f"{record['incident']}: absent evidence must be prose"
            assert not entry.startswith(
                ("logs:", "metrics:", "deploys:", "deps:", "runbook:", "postmortem:")
            ), f"{record['incident']}: absent evidence must not be written as a reference"


# --- shape: the record is authored, so nothing else guards its structure -----------------------
def test_one_golden_record_per_authored_incident():
    golden_ids = [record["incident"] for record in GOLDEN]
    scenario_ids = [scenario["id"] for scenario in SCENARIOS]
    assert sorted(golden_ids) == sorted(scenario_ids), (
        "every authored incident carries exactly one golden record, and nothing else does"
    )
    assert len(golden_ids) == len(set(golden_ids)), "duplicate golden record"


def test_every_record_carries_all_eight_parts():
    for record in GOLDEN:
        missing = REQUIRED_PARTS - set(record)
        assert not missing, f"{record['incident']}: missing {sorted(missing)}"


def test_scenario_classes_are_from_the_accepted_set():
    for record in GOLDEN:
        assert record["classes"], f"{record['incident']}: at least one class"
        unknown = set(record["classes"]) - ACCEPTED_CLASSES
        assert not unknown, f"{record['incident']}: unknown scenario class {sorted(unknown)}"


def test_expected_outcome_shapes_are_from_the_accepted_vocabulary():
    for record in GOLDEN:
        assert record["expected_outcome_shape"], f"{record['incident']}: at least one shape"
        unknown = set(record["expected_outcome_shape"]) - ACCEPTED_OUTCOMES
        assert not unknown, f"{record['incident']}: unknown outcome shape {sorted(unknown)}"


def test_every_required_evidence_group_states_what_it_establishes():
    # The group exists so that two valid evidence paths reaching the same fact both count. A
    # group with no stated claim is an ordered checklist wearing a group's clothes.
    for record in GOLDEN:
        assert record["required_evidence"], f"{record['incident']}: required evidence is empty"
        for group in record["required_evidence"]:
            assert group.get("establishes"), f"{record['incident']}: group without `establishes`"
            assert group.get("any_of") or group.get("all_of"), (
                f"{record['incident']}: group '{group.get('establishes')}' names no references"
            )


def test_the_multi_contributor_scenario_requires_two_independent_conditions():
    # The class is only genuinely represented if the record demands both contributing signals
    # separately. One group covering both would let a single-cause answer satisfy it.
    record = next(r for r in GOLDEN if "multiple_contributing_failures" in r["classes"])
    condition_groups = [
        g for g in record["required_evidence"] if "contributing condition" in g["establishes"]
    ]
    assert len(condition_groups) >= 2, (
        f"{record['incident']}: the multi-contributor class needs two independently "
        "established contributing conditions, not one combined group"
    )
    entities = {
        ref.split(":")[1]
        for g in condition_groups
        for ref in g.get("all_of", []) + g.get("any_of", [])
    }
    assert len(entities) >= 2, f"{record['incident']}: contributing conditions share one entity"


def test_the_red_herring_is_required_evidence_not_an_excluded_reference():
    # inc-004's coincidental deploy must be reached and then cleared. A golden record that
    # omitted it would score an investigation as correct for never looking.
    record = next(r for r in GOLDEN if r["incident"] == "inc-004")
    red_herring = next(s for s in SCENARIOS if s["id"] == "inc-004")["red_herring"]
    assert red_herring in _all_references(record), (
        "the red herring must appear as evidence a correct investigation reaches"
    )
