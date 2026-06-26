"""Phase 1 state-contract test — the inter-node contract must hold.

This is the single Track A test that matters at this stage: LangGraph's inter-node
contract is the silent-failure point, so we validate the end-to-end stubbed flow produces
a report that satisfies the Pydantic contract.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from opspilot.contracts import IncidentReport  # noqa: E402
from opspilot.graph import _initial_state, build_graph  # noqa: E402


def _run(alert: dict) -> dict:
    return build_graph().invoke(_initial_state(alert))


def test_full_stubbed_flow_produces_valid_report() -> None:
    result = _run({"incident_id": "INC-1", "severity": "SEV2", "summary": "5xx spike after deploy"})

    # The report must satisfy the Pydantic contract — the silent-failure guard.
    report = IncidentReport.model_validate(result["report"])
    assert report.incident_id == "INC-1"
    assert report.severity == "SEV2"
    assert 0.0 <= report.confidence <= 1.0
    assert report.citations  # evidence was retrieved and cited
    assert report.evidence  # at least one evidence item


def test_flow_completes_through_approval_and_postmortem() -> None:
    result = _run({"incident_id": "INC-2", "summary": "latency regression"})
    assert result["approval"]["decision"] == "approve"
    assert result["postmortem"]["incident_id"] == "INC-2"
