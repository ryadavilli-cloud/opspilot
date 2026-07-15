"""Step 2 gate: deterministic ingest + triage routes every scenario correctly.

Runs only the front of the graph (ingest -> triage_router -> route decision) for all six
scenarios and checks: historical incidents take the known-incident route, novel ones take the
diagnostic route, the derived severity/category/affected-services match, and the decision records
the evidence behind it. Skipped without the retrieval extras (triage uses search_past_incidents).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("sentence_transformers")
pytest.importorskip("rank_bm25")

from opspilot.nodes.investigation import ingest, triage_router  # noqa: E402
from opspilot.router import route_by_intent  # noqa: E402
from opspilot.state import InvestigationState  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_bg = _load("build_goldens", "data/answer_key/build_goldens.py")
SCENARIOS = _bg.load_scenarios()
TOPOLOGY = _bg.load_topology()
ENTITIES = (
    {s["id"] for s in TOPOLOGY["services"]}
    | {i["id"] for i in TOPOLOGY["infra"]}
    | {e["id"] for e in TOPOLOGY["externals"]}
)


def _front(scenario) -> tuple[InvestigationState, str]:
    alert = {"incident_id": scenario["id"], "summary": scenario["alert"]["summary"]}
    state = InvestigationState(alert=alert)
    state = state.model_copy(update=ingest(state))
    state = state.model_copy(update=triage_router(state))
    return state, route_by_intent(state)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s["id"])
def test_ingest_triage_routes_and_classifies(scenario):
    state, route = _front(scenario)

    expected_route = "known_issue_fast_path" if scenario["type"] == "historical" else "retrieve"
    assert route == expected_route, f"{scenario['id']}: routed to {route}"

    assert state.intent == scenario["expected_intent"]
    assert (state.matched_incident or None) == scenario["expected_match"]
    assert state.severity == scenario["severity"]
    assert state.category == scenario["category"]

    # Derived affected services are real topology entities from the alert storm.
    assert state.affected_services and all(s in ENTITIES for s in state.affected_services)
    assert state.onset

    # The decision records the evidence that caused it.
    triage = state.triage
    assert triage["top_past_incidents"]  # the candidates the decision weighed
    if scenario["type"] == "historical":
        assert triage["matched_incident"] == f"postmortem:{scenario['id']}"
    else:
        assert triage["matched_incident"] == ""
