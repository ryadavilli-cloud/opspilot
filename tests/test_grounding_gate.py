"""The grounding gate: what makes an assessment unsafe to deliver, and what does not.

Every case here is reachable by a normally-constructed assessment, because nothing upstream
pre-enforces these properties any more. That is the arrangement worth protecting: the gate is the
only place that decides whether a claim rests on something this run observed, so a test that had to
bypass a validator to reach a failure branch would be testing defense in depth rather than the one
decision that matters.

Resolution is deliberately checked against the run rather than against the reference's own shape. A
perfectly well-formed reference to a real record is still ungrounded if this investigation never
admitted it, and that is the failure a model is most able to produce.
"""

from __future__ import annotations

from opspilot.assessment.contracts import Action, Assessment, Candidate, SupportLabel
from opspilot.evidence.admission import Limitation
from opspilot.grounding.gate import (
    KNOWLEDGE_AS_SUPPORT,
    UNDISCLOSED_LIMITATION,
    UNRESOLVED_REFERENCE,
    UNSUPPORTED_CLAIM,
    ground,
)
from opspilot.tools.contracts import ExecutionOutcome

LOG = "logs:checkout-api:evt-1"
DEPLOY = "deploys:checkout-api:d-1"
RUNBOOK = "runbook:checkout-timeout"
POSTMORTEM = "postmortem:inc-001"


def _candidate(*, established: bool = True, supporting=(LOG,), weakening=()) -> Candidate:
    return Candidate(
        statement="a bad deploy caused it",
        label=SupportLabel.LEADING,
        established=established,
        supporting=list(supporting),
        weakening=list(weakening),
    )


def _assessment(**overrides) -> Assessment:
    base = dict(
        what_happened="checkout latency rose",
        what_happened_refs=[LOG],
        candidates=[_candidate()],
    )
    base.update(overrides)
    return Assessment(**base)


def _limitation(question: str = "what did the change history show") -> Limitation:
    return Limitation(
        question=question,
        reason="the source could not be reached",
        operation_ref="op-1",
        capability="get_deployments",
        outcome=ExecutionOutcome.UNAVAILABLE,
    )


def _kinds(issues) -> list[str]:
    return [issue.kind for issue in issues]


# --- a clean assessment ---------------------------------------------------------------------
def test_a_grounded_assessment_yields_no_issues():
    limitation = _limitation()
    assessment = _assessment(
        limitations=[limitation.question],
        knowledge_used=[RUNBOOK],
        actions=[Action(action="roll back", now=True, knowledge_ref=RUNBOOK)],
    )

    assert (
        ground(
            assessment,
            admitted_refs={LOG},
            knowledge_refs={RUNBOOK},
            limitations=[limitation],
        )
        == []
    )


# --- references resolve against this run ------------------------------------------------------
def test_an_operational_reference_this_run_never_admitted_is_an_issue():
    issues = ground(_assessment(candidates=[_candidate(supporting=[DEPLOY])]), admitted_refs={LOG})

    assert UNRESOLVED_REFERENCE in _kinds(issues)
    assert any(DEPLOY in issue.detail for issue in issues)


def test_a_weakening_reference_is_resolved_like_any_other():
    """Contradicting evidence is kept and shown, which means it has to name something real too."""
    issues = ground(_assessment(candidates=[_candidate(weakening=[DEPLOY])]), admitted_refs={LOG})

    assert any(issue.kind == UNRESOLVED_REFERENCE and DEPLOY in issue.detail for issue in issues)


def test_a_knowledge_reference_this_run_never_retrieved_is_an_issue():
    issues = ground(
        _assessment(knowledge_used=[POSTMORTEM]), admitted_refs={LOG}, knowledge_refs={RUNBOOK}
    )

    unresolved = [i for i in issues if i.kind == UNRESOLVED_REFERENCE]
    assert any(POSTMORTEM in issue.detail for issue in unresolved)


def test_an_actions_knowledge_reference_is_resolved_too():
    """An action that claims a runbook supplied it is making a checkable claim about provenance."""
    issues = ground(
        _assessment(actions=[Action(action="roll back", now=True, knowledge_ref=RUNBOOK)]),
        admitted_refs={LOG},
        knowledge_refs=set(),
    )

    assert any(issue.kind == UNRESOLVED_REFERENCE and RUNBOOK in issue.detail for issue in issues)


def test_a_history_reference_this_run_never_retrieved_is_an_issue():
    issues = ground(
        _assessment(history="this happened before", history_refs=[POSTMORTEM]),
        admitted_refs={LOG},
        knowledge_refs={RUNBOOK},
    )

    unresolved = [i for i in issues if i.kind == UNRESOLVED_REFERENCE]
    assert any(POSTMORTEM in issue.detail for issue in unresolved)


# --- knowledge can never stand as current proof -----------------------------------------------
def test_a_knowledge_reference_offered_as_current_support_is_an_issue():
    """A document cannot observe the running system. Retrieving it does not make it proof, so this
    stays an issue even when the passage really was retrieved."""
    issues = ground(
        _assessment(candidates=[_candidate(supporting=[RUNBOOK])]),
        admitted_refs={LOG},
        knowledge_refs={RUNBOOK},
    )

    assert KNOWLEDGE_AS_SUPPORT in _kinds(issues)


def test_knowledge_offered_as_support_for_what_happened_is_an_issue():
    issues = ground(
        _assessment(what_happened_refs=[RUNBOOK]), admitted_refs={LOG}, knowledge_refs={RUNBOOK}
    )

    assert KNOWLEDGE_AS_SUPPORT in _kinds(issues)


# --- material claims rest on admitted evidence ------------------------------------------------
def test_what_happened_without_operational_support_is_an_issue():
    """It is itself a material statement about the incident, so it needs support like any other."""
    issues = ground(_assessment(what_happened_refs=[]), admitted_refs={LOG})

    assert UNSUPPORTED_CLAIM in _kinds(issues)
    assert any("what_happened" in issue.detail for issue in issues)


def test_an_established_candidate_without_admitted_support_is_an_issue():
    issues = ground(_assessment(candidates=[_candidate(supporting=[])]), admitted_refs={LOG})

    unsupported = [i for i in issues if i.kind == UNSUPPORTED_CLAIM]
    assert any("established" in issue.detail for issue in unsupported)


def test_a_candidate_left_open_needs_no_support():
    """Only what the brief may present as current fact has to rest on something observed. An
    explanation the evidence keeps open is allowed to be exactly that."""
    issues = ground(
        _assessment(candidates=[_candidate(established=False, supporting=[])]), admitted_refs={LOG}
    )

    assert UNSUPPORTED_CLAIM not in _kinds(issues)


# --- limitations are disclosed ------------------------------------------------------------------
def test_a_recorded_limitation_the_assessment_omits_is_an_issue():
    recorded = _limitation()
    issues = ground(_assessment(limitations=[]), admitted_refs={LOG}, limitations=[recorded])

    assert UNDISCLOSED_LIMITATION in _kinds(issues)
    assert any(recorded.question in issue.detail for issue in issues)


def test_disclosing_more_than_was_recorded_is_not_an_issue():
    """Only an omission understates what the run could not establish."""
    issues = ground(
        _assessment(limitations=["something the run never recorded"]),
        admitted_refs={LOG},
        limitations=[],
    )

    assert UNDISCLOSED_LIMITATION not in _kinds(issues)


# --- the gate reports, and does nothing else ----------------------------------------------------
def test_the_gate_reports_every_issue_not_only_the_first():
    issues = ground(
        _assessment(what_happened_refs=[], candidates=[_candidate(supporting=[DEPLOY])]),
        admitted_refs={LOG},
        limitations=[_limitation()],
    )

    assert set(_kinds(issues)) == {UNSUPPORTED_CLAIM, UNRESOLVED_REFERENCE, UNDISCLOSED_LIMITATION}


def test_the_gate_does_not_edit_the_assessment():
    """It reports; correcting is a separate decision made elsewhere with a model call."""
    assessment = _assessment(candidates=[_candidate(supporting=[DEPLOY])])
    before = assessment.model_dump()

    ground(assessment, admitted_refs={LOG})

    assert assessment.model_dump() == before
