"""The benign/transient controlled fixture must resolve, and must stay structurally distinct
from the seven authored incidents: no shared event id, no incident record, and none of the
expectations that only an incident can have. A fixture that quietly drifted into looking like an
eighth incident would defeat the reason it exists.

It does carry an expectation of its own, because the evaluation checks that a run shown something
which recovered on its own says so. That expectation holds only what applies to it: an accepted
outcome and the requirement of an affirmative no-action-now answer, never an expected cause or
evidence a correct run must reach, because it has neither.
"""

from __future__ import annotations

import json
from pathlib import Path

from answer_key import FIXTURE, SCENARIOS

REPO_ROOT = Path(__file__).resolve().parents[1]
SYN = REPO_ROOT / "data" / "synthetic"

LOGS = [json.loads(line) for line in (SYN / "logs.jsonl").read_text(encoding="utf-8").splitlines()]
LOG_BY_EVENT = {r["event_id"]: r for r in LOGS}

SCENARIO_EVENT_IDS = {
    ref.rsplit(":", 1)[1]
    for s in SCENARIOS
    for ref in s["expected_evidence"]
    if ref.startswith("logs:")
}


def test_fixture_carries_none_of_the_expectations_only_an_incident_can_have():
    assert FIXTURE["expected_behavior"] == "no_investigation_warranted"
    for absent in ("expected_evidence", "expected_match", "expected_cause", "resolution"):
        assert absent not in FIXTURE, f"fixture carries {absent}, which belongs to an incident"


def test_fixture_expects_only_what_applies_to_it():
    """The scenario shape would make the set uniform by inventing expectations it cannot have."""
    assert set(FIXTURE["evaluation"]) == {
        "accepted_outcomes",
        "requires_no_immediate_action",
        "behavior_tested",
    }
    assert FIXTURE["evaluation"]["requires_no_immediate_action"] is True


def test_the_row_the_fixture_is_reported_from_is_one_of_its_own():
    """The evaluation runs one of the four and derives the context from it, so a `reported_from`
    naming anything else would evaluate a symptom this class does not represent."""
    assert f"logs:catalog-api:{FIXTURE['reported_from']}" in FIXTURE["derived_from"]


def test_derived_rows_resolve_and_carry_no_incident():
    assert FIXTURE["derived_from"], "fixture cites no ambient rows"
    for ref in FIXTURE["derived_from"]:
        source, rest = ref.split(":", 1)
        assert source == "logs"
        svc, event_id = rest.rsplit(":", 1)
        row = LOG_BY_EVENT.get(event_id)
        assert row is not None, f"{ref} does not resolve to a generated log row"
        assert row["service"] == svc, f"{ref}: service mismatch"
        assert row["incident_id"] is None, f"{ref}: carries an incident_id, not ambient noise"
        assert row.get("label") == "non_incident", f"{ref}: not labeled non_incident"


def test_fixture_rows_are_disjoint_from_every_authored_incident():
    fixture_event_ids = {ref.rsplit(":", 1)[1] for ref in FIXTURE["derived_from"]}
    overlap = fixture_event_ids & SCENARIO_EVENT_IDS
    assert not overlap, f"benign fixture rows also cited as incident evidence: {overlap}"


def test_fixture_is_not_an_eighth_incident():
    assert len(SCENARIOS) == 7, "benign fixture must not be counted alongside the scenarios"
    assert all(s["id"] != FIXTURE["id"] for s in SCENARIOS)
