"""State-contract test: the inter-node contract must hold end to end.

An integration test: the graph runs real retrieval (over a fake Cosmos container, so no live Azure
dependency) plus deterministic triage/diagnosis, against real scenarios. LangGraph's inter-node
contract is the silent-failure point, so we validate the full flow produces a report satisfying the
Pydantic contract on both the novel (diagnose) and known-issue (fast-path) routes.
"""

from fake_knowledge import knowledge_retriever
from fake_operational_records import corpus_records

from opspilot.contracts import IncidentReport
from opspilot.graph import _initial_state, build_graph, invoke_auto_approving
from opspilot.tools.service import ToolService


def _run(alert: dict) -> dict:
    config = {
        "configurable": {
            "tool_service": ToolService(corpus_records(), retriever_factory=knowledge_retriever),
            "thread_id": f"state-contract-{alert['incident_id']}",
        }
    }
    return invoke_auto_approving(build_graph(), _initial_state(alert), config=config)


def test_novel_scenario_produces_valid_cited_report() -> None:
    result = _run(
        {"incident_id": "inc-006", "summary": "Reservation conflicts and oversells at checkout."}
    )

    report = IncidentReport.model_validate(result["report"])  # the silent-failure guard
    assert report.incident_id == "inc-006"
    assert report.severity == "SEV2"
    assert 0.0 <= report.confidence <= 1.0
    assert report.citations and report.evidence
    assert "deployment" in report.hypothesis.lower()  # the deterministic diagnosis fired


def test_known_issue_scenario_fast_paths_through_approval_and_postmortem() -> None:
    result = _run(
        {
            "incident_id": "inc-001",
            "summary": "Elevated checkout failures; payment authorizations timing out.",
        }
    )

    assert result["approval"]["decision"] == "approve"
    assert result["postmortem"]["incident_id"] == "inc-001"
    report = IncidentReport.model_validate(result["report"])
    assert report.citations


def test_evidence_is_deduplicated_and_ids_are_separated() -> None:
    result = _run(
        {"incident_id": "inc-006", "summary": "Reservation conflicts and oversells at checkout."}
    )

    # the content-hash reducer guarantees one entry per distinct piece of evidence
    refs = [item.ref for item in result["evidence_by_id"].values()]
    assert refs and len(refs) == len(set(refs)), f"duplicate evidence refs: {refs}"

    # identifiers are separated — investigation_id/thread_id are minted, not the incident id
    assert result["incident_id"] == "inc-006"
    assert result["investigation_id"] and result["investigation_id"] != result["incident_id"]
    assert result["thread_id"] == f"thread-{result['investigation_id']}"
