"""2a consistency gate for the RetailEase answer key.

Scoped to what exists at Phase 2a: the answer key's *internal* coherence and its agreement
with the committed golden sets. The full cross-corpus closure check (every evidence ref
resolves to a generated telemetry row; every retrieval id exists as a KB doc) is Phase 2e,
once 2b/2d exist. Until then this guards the spine: schema, ref grammar, topology references,
intent/match invariants, and goldens-in-sync.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ANSWER_KEY_DIR = REPO_ROOT / "data" / "answer_key"

# Import build_goldens.py by path (it lives under data/, not on the package path).
_spec = importlib.util.spec_from_file_location("build_goldens", ANSWER_KEY_DIR / "build_goldens.py")
assert _spec and _spec.loader
build_goldens = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_goldens)

TOPOLOGY = build_goldens.load_topology()
SCENARIOS = build_goldens.load_scenarios()

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
    assert len(SCENARIOS) == 6
    assert len(HISTORICAL_IDS) == 3
    assert sum(1 for s in SCENARIOS if s["type"] == "novel") == 3


def test_scenarios_have_required_fields_and_controlled_vocab():
    required = {
        "id", "title", "type", "severity", "category", "occurred_at", "alert",
        "expected_intent", "expected_match", "trigger", "root_cause",
        "impacted_chain", "expected_evidence", "expected_retrieval",
    }
    seen_ids = set()
    for s in SCENARIOS:
        missing = required - s.keys()
        assert not missing, f"{s.get('id')} missing fields: {missing}"
        assert s["id"] not in seen_ids, f"duplicate id {s['id']}"
        seen_ids.add(s["id"])
        assert s["type"] in {"historical", "novel"}
        assert s["severity"] in SEVERITIES
        assert s["category"] in CATEGORIES, f"{s['id']} unknown category {s['category']}"


def test_intent_and_match_invariants():
    for s in SCENARIOS:
        if s["type"] == "historical":
            assert s["expected_intent"] == "known_issue", s["id"]
            assert s["expected_match"] == f"postmortem:{s['id']}", s["id"]
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


def test_retrieval_ids_follow_namespaces():
    for s in SCENARIOS:
        for ref in s["expected_retrieval"]:
            ns, ident = ref.split(":", 1)
            assert ns in RETRIEVAL_NAMESPACES, f"{s['id']}: bad retrieval namespace in {ref!r}"
            if ns == "postmortem":
                assert ident in HISTORICAL_IDS, f"{s['id']}: no historical incident {ident}"


def test_committed_goldens_match_projection():
    """Drift gate: the committed JSON must equal a fresh projection of the answer key."""
    fresh_incidents = build_goldens.build_incident_goldens(SCENARIOS)
    fresh_retrieval = build_goldens.build_retrieval_goldens(SCENARIOS)
    committed_incidents = json.loads(
        build_goldens.GOLDEN_INCIDENTS_PATH.read_text(encoding="utf-8")
    )
    committed_retrieval = json.loads(
        build_goldens.GOLDEN_RETRIEVAL_PATH.read_text(encoding="utf-8")
    )
    assert committed_incidents == fresh_incidents, "golden_incidents.json stale — rerun builder"
    assert committed_retrieval == fresh_retrieval, "golden_retrieval.json stale — rerun builder"
