"""The record seam: one investigation, one save, one read.

Two properties carry the weight. An investigation is saved once, so a repeat is refused rather than
overwriting the first account of it. And a save that fails raises rather than returning a status a
caller could forget to read, because the one thing that must never happen is delivering a brief
whose record was never written.
"""

from __future__ import annotations

import pytest

from opspilot.assessment.contracts import Assessment, Brief, Candidate, Outcome, SupportLabel
from opspilot.record.completed import CompletedInvestigation
from opspilot.record.memory import InMemoryInvestigationRecord
from opspilot.record.port import RecordSaveError


def _completed(investigation_id: str = "inv-1") -> CompletedInvestigation:
    assessment = Assessment(
        what_happened="checkout latency rose",
        what_happened_refs=["logs:checkout-api:evt-1"],
        candidates=[
            Candidate(
                statement="the cache evicted session keys",
                label=SupportLabel.LEADING,
                established=True,
                supporting=["logs:checkout-api:evt-1"],
            )
        ],
    )
    return CompletedInvestigation(
        investigation_id=investigation_id,
        incident_id="inc-005",
        objective="establish why checkout latency rose",
        outcome=Outcome.COMPLETE,
        stopped_because="the evidence was ready to interpret",
        assessment=assessment,
        brief=Brief(outcome=Outcome.COMPLETE, text="Outcome: complete"),
        model_deployment="gpt-5-mini",
    )


def test_a_saved_investigation_reads_back_as_itself():
    record = InMemoryInvestigationRecord()
    saved = _completed()

    record.save(saved)

    assert record.get("inv-1") == saved


def test_an_unsaved_identifier_reads_as_nothing():
    """Not an error and not an empty record: no investigation was ever completed under it."""
    assert InMemoryInvestigationRecord().get("inv-nope") is None


def test_a_second_save_of_the_same_investigation_is_refused():
    """One investigation is one run and one record. A repeat is a defect upstream, and overwriting
    would destroy the first account of it."""
    record = InMemoryInvestigationRecord()
    record.save(_completed())

    with pytest.raises(RecordSaveError, match="already saved"):
        record.save(_completed())


def test_an_investigation_without_an_identifier_is_refused():
    record = InMemoryInvestigationRecord()

    with pytest.raises(RecordSaveError, match="needs an identifier"):
        record.save(_completed(investigation_id=""))


def test_nothing_exists_before_the_first_save():
    """Starting an investigation persists nothing, so an abandoned run leaves no shell behind."""
    record = InMemoryInvestigationRecord()
    assert record.get("inv-1") is None
    record.save(_completed())
    assert record.get("inv-1") is not None
