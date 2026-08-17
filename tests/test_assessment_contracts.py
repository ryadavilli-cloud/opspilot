"""The assessment shape.

Almost nothing is asserted here, and that is the point: the shape holds no invariant about whether
a claim is supported, because grounding owns that question alone. What remains are the two
properties the shape itself must carry, both of which are ways an assessment could quietly claim
more than its evidence supports: a number acting as confidence, and support expressed by anything
other than the labels.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from opspilot.assessment.contracts import (
    Action,
    Assessment,
    Brief,
    Candidate,
    Outcome,
    SupportLabel,
)

EVIDENCE = "metrics:redis-cache:used_memory_pct@2026-06-22T11:35:00Z"


def _candidate(established: bool = True, statement: str = "the cache evicted session keys"):
    return Candidate(
        statement=statement,
        label=SupportLabel.LEADING,
        established=established,
        supporting=[EVIDENCE],
    )


def _numeric_fields(model: type[BaseModel]) -> list[str]:
    found: list[str] = []
    for name, field in model.model_fields.items():
        annotation = str(field.annotation)
        if "float" in annotation or "Decimal" in annotation:
            found.append(f"{model.__name__}.{name}")
    return found


@pytest.mark.parametrize("model", [Assessment, Candidate, Action, Brief])
def test_no_shape_carries_a_number_that_could_act_as_confidence(model):
    """Model confidence is not a form of support. A float on any of these would become one the
    moment something sorted or thresholded on it."""
    assert _numeric_fields(model) == []


def test_support_is_expressed_only_by_the_three_labels():
    assert [label.value for label in SupportLabel] == ["leading", "plausible", "weakly_supported"]


def test_established_names_the_candidates_the_brief_may_present_as_fact():
    assessment = Assessment(
        candidates=[_candidate(), _candidate(established=False, statement="a slow dependency")]
    )
    assert [c.statement for c in assessment.established] == ["the cache evicted session keys"]


def test_an_assessment_is_frozen():
    """One assessment per investigation, and nothing edits it after the gate reads it."""
    assessment = Assessment(what_happened="checkout latency rose")
    with pytest.raises(Exception, match="frozen"):
        assessment.what_happened = "something else"  # type: ignore[misc]


def test_the_outcome_vocabulary_is_the_three_the_design_names():
    assert [outcome.value for outcome in Outcome] == ["complete", "partial", "inconclusive"]
