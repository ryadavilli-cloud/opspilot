"""Consistency gate for the RetailEase answer key.

Scoped to the answer key's *internal* coherence. The full cross-corpus closure check (every
evidence ref resolves to a generated telemetry row; every retrieval id exists as a KB doc) belongs
to `test_closure.py`. This guards the spine: schema, ref grammar, topology references,
intent and match invariants, and the evaluation expectation each scenario carries.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
ANSWER_KEY_DIR = REPO_ROOT / "data" / "answer_key"


def _authored(name: str):
    return yaml.safe_load((ANSWER_KEY_DIR / name).read_text(encoding="utf-8"))


TOPOLOGY = _authored("topology.yaml")
SCENARIOS = _authored("scenarios.yaml")["scenarios"]

SERVICES = {s["id"] for s in TOPOLOGY["services"]}
INFRA = {i["id"] for i in TOPOLOGY["infra"]}
EXTERNALS = {e["id"] for e in TOPOLOGY["externals"]}
ENTITIES = SERVICES | INFRA | EXTERNALS
DEP_EDGES = {f"{d['from']}->{d['to']}" for d in TOPOLOGY["dependencies"]}

EVIDENCE_SOURCES = {"logs", "metrics", "deploys", "deps"}  # frozen Evidence.source (telemetry half)
RETRIEVAL_NAMESPACES = {"runbook", "architecture", "postmortem"}
SEVERITIES = {"SEV1", "SEV2", "SEV3", "SEV4"}
CATEGORIES = {"payment", "datastore", "messaging", "cache", "inventory"}

TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T(\d{2}):(\d{2}):\d{2}Z$")
HISTORICAL_IDS = {s["id"] for s in SCENARIOS if s["type"] == "historical"}


def _evidence_entity(ref: str) -> str:
    """The service/infra token an evidence ref points at, for topology validation."""
    source, rest = ref.split(":", 1)
    if source == "deps":
        return rest  # "<from>-><to>"
    if source == "metrics":
        return rest.split(":", 1)[0]  # "<service>:<metric>@<ts>"
    return rest.rsplit(":", 1)[0]  # logs/deploys: "<service>:<id>"


def test_scenario_count_and_split():
    assert len(SCENARIOS) == 7
    assert len(HISTORICAL_IDS) == 3
    assert sum(1 for s in SCENARIOS if s["type"] == "novel") == 3
    assert sum(1 for s in SCENARIOS if s["type"] == "recurrence") == 1


def test_scenarios_have_required_fields_and_controlled_vocab():
    required = {
        "id",
        "title",
        "type",
        "severity",
        "category",
        "occurred_at",
        "alert",
        "expected_intent",
        "expected_match",
        "trigger",
        "root_cause",
        "impacted_chain",
        "expected_evidence",
        "expected_retrieval",
    }
    seen_ids = set()
    for s in SCENARIOS:
        missing = required - s.keys()
        assert not missing, f"{s.get('id')} missing fields: {missing}"
        assert s["id"] not in seen_ids, f"duplicate id {s['id']}"
        seen_ids.add(s["id"])
        assert s["type"] in {"historical", "novel", "recurrence"}
        assert s["severity"] in SEVERITIES
        assert s["category"] in CATEGORIES, f"{s['id']} unknown category {s['category']}"


def test_intent_and_match_invariants():
    for s in SCENARIOS:
        if s["type"] == "historical":
            assert s["expected_intent"] == "known_issue", s["id"]
            assert s["expected_match"] == f"postmortem:{s['id']}", s["id"]
        elif s["type"] == "recurrence":
            # A genuine recurrence: the truth is a known issue, matched to ANOTHER incident's
            # postmortem — matching itself is the untestable loophole this type exists to close.
            assert s["expected_intent"] == "known_issue", s["id"]
            match = s["expected_match"]
            assert match and match.startswith("postmortem:"), s["id"]
            assert match != f"postmortem:{s['id']}", f"{s['id']}: recurrence must not self-match"
            assert match.split(":", 1)[1] in HISTORICAL_IDS, s["id"]
        else:
            assert s["expected_intent"] == "novel_investigation", s["id"]
            assert s["expected_match"] is None, s["id"]


def test_impacted_chain_entities_exist():
    for s in SCENARIOS:
        for ent in s["impacted_chain"]:
            assert ent in ENTITIES, f"{s['id']} chain references unknown entity {ent}"


def test_evidence_refs_follow_grammar_and_topology():
    for s in SCENARIOS:
        for ref in s["expected_evidence"]:
            source = ref.split(":", 1)[0]
            assert source in EVIDENCE_SOURCES, f"{s['id']}: bad evidence source in {ref!r}"
            entity = _evidence_entity(ref)
            if source == "deps":
                assert entity in DEP_EDGES, f"{s['id']}: {ref!r} is not a real dependency edge"
            elif source == "metrics":
                assert entity in SERVICES | INFRA, f"{s['id']}: metrics entity {entity} unknown"
                m = TS_RE.search(ref)
                assert m, f"{s['id']}: metrics ref {ref!r} lacks a valid @<ts>"
                assert int(m.group(2)) % 5 == 0, f"{s['id']}: {ref!r} off 5-min boundary"
            elif source == "deploys":
                assert entity in SERVICES, f"{s['id']}: only owned services deploy, got {entity}"
            else:  # logs
                assert entity in SERVICES, f"{s['id']}: logs entity {entity} not a service"


def test_red_herring_is_declared_evidence():
    for s in SCENARIOS:
        rh = s.get("red_herring")
        if rh is not None:
            assert rh in s["expected_evidence"], f"{s['id']}: red_herring must also be in evidence"


def test_inc_006_represents_multiple_independent_contributing_signals():
    """inc-006 is the corpus's multi-contributor representative. Relabeling a single linear
    chain as "multi-contributor" without a second
    independently observable signal would not actually close the coverage gap, so this
    checks structure, not prose: contributing metric evidence must span at least two
    distinct entities."""
    inc6 = next(s for s in SCENARIOS if s["id"] == "inc-006")
    metric_entities = {
        ref.split(":", 2)[1] for ref in inc6["expected_evidence"] if ref.startswith("metrics:")
    }
    assert len(metric_entities) >= 2, (
        "inc-006 must evidence contributing signals on at least two distinct entities"
    )


def test_retrieval_ids_follow_namespaces():
    for s in SCENARIOS:
        for ref in s["expected_retrieval"]:
            ns, ident = ref.split(":", 1)
            assert ns in RETRIEVAL_NAMESPACES, f"{s['id']}: bad retrieval namespace in {ref!r}"
            if ns == "postmortem":
                assert ident in HISTORICAL_IDS, f"{s['id']}: no historical incident {ident}"


# --- what a correct investigation looks like ------------------------------------------------------
# The evaluation expectation, held to its shape here so the runner can read it without guarding
# every field. What each expectation means is authored; that all seven state one is structural.
ACCEPTED_OUTCOMES = {"complete", "partial", "inconclusive"}
EVALUATION_FIELDS = {
    "acceptable_alternatives",
    "absent_evidence",
    "accepted_outcomes",
    "behavior_tested",
    "knowledge_should",
    "expected_recommendation",
}
# Stated only where a competing hypothesis is worth ruling out. Requiring it of all seven would
# mean authoring one for scenarios that have none, which is an expectation nobody holds.
OPTIONAL_EVALUATION_FIELDS = {"weakens_candidate"}


def test_every_scenario_states_what_a_correct_investigation_looks_like():
    for s in SCENARIOS:
        evaluation = s.get("evaluation")
        assert evaluation, f"{s['id']}: no evaluation expectation"
        missing = EVALUATION_FIELDS - evaluation.keys()
        assert not missing, f"{s['id']}: expectation missing {missing}"
        extra = evaluation.keys() - EVALUATION_FIELDS - OPTIONAL_EVALUATION_FIELDS
        assert not extra, f"{s['id']}: expectation carries unknown fields {extra}"


def test_accepted_outcomes_are_outcomes_the_runtime_can_reach():
    """An expectation naming an outcome the runtime never produces could not be met by a correct
    run, and would read as the scenario failing rather than as the expectation being wrong."""
    for s in SCENARIOS:
        accepted = s["evaluation"]["accepted_outcomes"]
        assert accepted, f"{s['id']}: accepts no outcome"
        unknown = set(accepted) - ACCEPTED_OUTCOMES
        assert not unknown, f"{s['id']}: accepts {unknown}, which no run can report"


def test_expectation_prose_is_stated_rather_than_left_empty():
    """Each of these is read by the judge or by a person; an empty one is an expectation nobody
    authored rather than one that does not apply."""
    for s in SCENARIOS:
        evaluation = s["evaluation"]
        for field in ("behavior_tested", "knowledge_should", "expected_recommendation"):
            assert evaluation[field].strip(), f"{s['id']}: {field} is empty"
        assert evaluation["acceptable_alternatives"], f"{s['id']}: no acceptable alternative stated"


def test_a_declared_absence_names_a_capability_the_registry_holds():
    """The absence is checked by asking a capability, so the expectation has to name one that
    exists. An empty list is the ordinary case and is not a gap."""
    from opspilot.tools import CAPABILITY_NAMES

    for s in SCENARIOS:
        for absence in s["evaluation"]["absent_evidence"]:
            assert absence["capability"] in CAPABILITY_NAMES, (
                f"{s['id']}: declares an absence of {absence['capability']}, "
                "which is not a capability"
            )
            assert absence["why"].strip(), (
                f"{s['id']}: absence stated without saying why it matters"
            )


def test_a_declared_absence_is_actually_absent_from_the_corpus():
    """The check that stops a regeneration quietly filling a gap a scenario depends on.

    inc-002 and inc-005 are authored so that nothing was deployed: their cause is a ceiling and a
    capacity limit, and an account reaching for a deploy has invented one. That only holds while
    the corpus really contains no such row, and the corpus is generated. Asked here through the
    same capability an investigation would use, over the window it would use.

    The outcome matters as much as the emptiness. A source that answers and holds nothing is an
    authoritative absence, which is evidence; a source that cannot answer is a limitation, which is
    not. A regeneration that made this capability unavailable would leave the list empty and the
    scenario meaningless, so both are asserted.
    """
    from datetime import datetime, timedelta

    from fake_operational_records import corpus_records

    from opspilot.tools.contracts import Completeness, ExecutionOutcome
    from opspilot.tools.service import ToolService

    service = ToolService(corpus_records())
    declared = [(s, a) for s in SCENARIOS for a in s["evaluation"]["absent_evidence"]]
    assert declared, "no scenario declares an absence, so this proves nothing"

    for scenario, absence in declared:
        raw = scenario["occurred_at"]
        at = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))
        result = service.call(
            absence["capability"],
            None,
            services=scenario["impacted_chain"],
            start_time=(at - timedelta(hours=12)).isoformat().replace("+00:00", "Z"),
            end_time=(at + timedelta(hours=12)).isoformat().replace("+00:00", "Z"),
        )
        assert result.outcome is ExecutionOutcome.SUCCEEDED, (
            f"{scenario['id']}: {absence['capability']} could not answer, so its silence is a "
            "limitation rather than the authoritative absence the scenario is authored around"
        )
        assert result.completeness is Completeness.EMPTY, (
            f"{scenario['id']}: the corpus now holds {len(result.results)} row(s) for "
            f"{absence['capability']}, which the scenario is authored to have none of: "
            f"{result.evidence_refs}"
        )
