"""The benign/transient controlled fixture must resolve, and must stay structurally distinct
from the seven authored incidents: no shared event id, no incident record, no scoreable
expectation. A fixture that quietly drifted into looking like an eighth incident would defeat
the reason it exists.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
ANSWER_KEY = REPO_ROOT / "data" / "answer_key"
SYN = REPO_ROOT / "data" / "synthetic"

_FIXTURE_TEXT = (ANSWER_KEY / "benign_fixture.yaml").read_text(encoding="utf-8")
FIXTURE = yaml.safe_load(_FIXTURE_TEXT)["fixture"]
SCENARIOS = yaml.safe_load((ANSWER_KEY / "scenarios.yaml").read_text(encoding="utf-8"))["scenarios"]
LOGS = [json.loads(line) for line in (SYN / "logs.jsonl").read_text(encoding="utf-8").splitlines()]
LOG_BY_EVENT = {r["event_id"]: r for r in LOGS}

SCENARIO_EVENT_IDS = {
    ref.rsplit(":", 1)[1]
    for s in SCENARIOS
    for ref in s["expected_evidence"]
    if ref.startswith("logs:")
}


def test_fixture_has_no_scoreable_expectation():
    assert FIXTURE["expected_match"] is None
    assert FIXTURE["expected_behavior"] == "no_investigation_warranted"
    assert "expected_evidence" not in FIXTURE
    assert "resolution" not in FIXTURE


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
