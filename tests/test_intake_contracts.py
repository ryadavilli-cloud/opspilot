"""The normalized incident context: four fields, and what must never appear beside them."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from opspilot.intake.contracts import NormalizedIncidentContext, from_predefined_incident
from opspilot.tools.contracts import IncidentRecord


def _incident(**overrides: object) -> IncidentRecord:
    fields = {
        "number": "INC0000001",
        "incident_id": "inc-001",
        "short_description": "Elevated checkout failures; payment authorizations timing out.",
        "category": "payment",
        "priority": "2 - High",
        "impact": "2 - Medium",
        "urgency": "1 - High",
        "opened_at": datetime(2026, 5, 12, 14, 30, tzinfo=UTC),
        "state": "Closed",
        "made_sla": False,
        "reassignment_count": 1,
        "is_known_error": True,
        "resolved_at": datetime(2026, 5, 12, 20, 30, tzinfo=UTC),
        "close_code": "Solved (Permanently)",
        "root_cause": "payment-api exhausted its Cosmos DB connection pool.",
        "resolution": "Reverted the connection-pool config to 100.",
    }
    fields.update(overrides)
    return IncidentRecord(**fields)


def test_a_raw_record_normalizes_to_exactly_the_four_fields():
    context = from_predefined_incident(_incident())
    assert context.incident_id == "inc-001"
    assert context.symptom == "Elevated checkout failures; payment authorizations timing out."
    assert context.time_anchor == datetime(2026, 5, 12, 14, 30, tzinfo=UTC)
    assert context.scope is None


def test_scope_is_never_populated_from_the_category():
    # A classification label is not a component identity, and populating scope from it would leak
    # the category as an answer hint. scope stays None unless the incident names one.
    context = from_predefined_incident(_incident(category="datastore"))
    assert context.scope is None


def test_from_predefined_incident_excludes_answer_key_content():
    context = from_predefined_incident(_incident())
    dumped = context.model_dump()
    assert "root_cause" not in dumped
    assert "resolution" not in dumped
    assert "close_code" not in dumped


def test_the_context_carries_no_ticket_workflow_fields():
    # No severity, priority, ownership, environment, ticket, or session field, and nothing that
    # would carry engineer-supplied text into an investigation ahead of admission.
    fields = set(NormalizedIncidentContext.model_fields)
    assert fields == {"incident_id", "scope", "symptom", "time_anchor"}


def test_an_incident_identity_is_required():
    """One investigation is one incident. A context without one could not name what it is about,
    and nothing downstream could key evidence, telemetry, or the record to it."""
    with pytest.raises(ValidationError):
        NormalizedIncidentContext(
            symptom="checkout errors", time_anchor=datetime(2026, 5, 12, tzinfo=UTC)
        )


def test_the_context_is_frozen():
    context = NormalizedIncidentContext(
        incident_id="inc-001",
        symptom="checkout errors",
        time_anchor=datetime(2026, 5, 12, tzinfo=UTC),
    )
    with pytest.raises(ValidationError):
        context.symptom = "tampered"
