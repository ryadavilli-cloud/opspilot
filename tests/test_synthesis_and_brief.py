"""Structural admission of a proposal, and the brief that renders what it produced.

The property under test throughout is that nothing between the model and the gate exercises
judgment. A candidate the run's evidence does not support still reaches the gate, because the gate
is what says so; a filter here would answer that question first and quietly, leaving the gate to
approve an assessment it never saw. What admission may refuse is structure: a response that is not
a proposal, and a string no reference grammar could produce.

The brief tests assert the symmetric rule: a rendering may not add what the assessment lacks, and
may not drop what it holds.
"""

from __future__ import annotations

import json

import pytest

from opspilot.assessment.brief import outcome_of, render
from opspilot.assessment.contracts import Action, Assessment, Candidate, Outcome, SupportLabel
from opspilot.assessment.synthesis import (
    ActionProposal,
    AssessmentProposal,
    CandidateProposal,
    UnusableProposal,
    admit_assessment,
    parse_proposal,
)

MEMORY = "metrics:redis-cache:used_memory_pct@2026-06-22T11:35:00Z"
EVICTED = "metrics:redis-cache:evicted_keys_rate@2026-06-22T11:40:00Z"
LOG = "logs:checkout-api:evt-005-01"
NEVER_ADMITTED = "logs:payment-api:evt-999-99"
RUNBOOK = "runbook:redis-cache-degradation"


def _proposal(**overrides) -> AssessmentProposal:
    base = dict(
        what_happened="checkout latency rose while the cache evicted keys",
        what_happened_refs=[LOG],
        candidates=[
            CandidateProposal(
                statement="redis-cache hit its memory ceiling and evicted session keys",
                label="leading",
                established=True,
                supporting=[MEMORY, EVICTED],
            )
        ],
        actions=[ActionProposal(action="raise the cache memory ceiling", now=True)],
    )
    base.update(overrides)
    return AssessmentProposal(**base)


def _candidate(statement: str, *, established: bool, label=SupportLabel.LEADING, **kw) -> Candidate:
    return Candidate(statement=statement, label=label, established=established, **kw)


# --- structural admission removes nothing -------------------------------------------------------
def test_a_reference_this_run_never_admitted_still_reaches_the_gate():
    """Whether a citation names something observed is the gate's question. Dropping it here would
    make the assessment look grounded to the very check that exists to say it is not."""
    proposal = _proposal(
        candidates=[
            CandidateProposal(
                statement="an invented cause",
                label="leading",
                established=True,
                supporting=[NEVER_ADMITTED],
            )
        ]
    )
    assessment = admit_assessment(proposal)
    assert assessment.candidates[0].supporting == [NEVER_ADMITTED]


def test_a_candidate_resting_on_nothing_is_not_removed():
    proposal = _proposal(
        candidates=[CandidateProposal(statement="a hunch", label="weakly_supported")]
    )
    assessment = admit_assessment(proposal)
    assert [c.statement for c in assessment.candidates] == ["a hunch"]
    assert assessment.candidates[0].supporting == []


def test_established_is_the_models_and_is_neither_derived_nor_downgraded():
    """Both directions. A candidate the model left open is not promoted because its references
    happen to be citable, and one it established is not demoted because they are not."""
    established = admit_assessment(
        _proposal(
            candidates=[
                CandidateProposal(
                    statement="c", label="leading", established=True, supporting=[NEVER_ADMITTED]
                )
            ]
        )
    )
    assert established.candidates[0].established is True

    open_candidate = admit_assessment(
        _proposal(
            candidates=[
                CandidateProposal(
                    statement="c", label="leading", established=False, supporting=[MEMORY]
                )
            ]
        )
    )
    assert open_candidate.candidates[0].established is False


def test_an_action_is_never_discarded_for_its_provenance():
    """Neither the one carrying retrieved guidance nor the one carrying none."""
    assessment = admit_assessment(
        _proposal(
            actions=[
                ActionProposal(
                    action="follow the eviction runbook", now=True, knowledge_ref=RUNBOOK
                ),
                ActionProposal(action="raise the memory ceiling", now=False),
            ]
        )
    )
    assert [a.knowledge_ref for a in assessment.actions] == [RUNBOOK, None]


def test_the_affirmative_no_action_entry_survives_as_an_entry():
    assessment = admit_assessment(
        _proposal(actions=[ActionProposal(action="no immediate action is required", now=True)])
    )
    assert assessment.actions[0].action == "no immediate action is required"
    assert assessment.actions[0].now is True


def test_recorded_limitations_and_unknowns_travel_as_the_analyst_stated_them():
    assessment = admit_assessment(
        _proposal(
            limitations=["what did the change history show", "  "],
            unknowns=["whether eviction preceded the latency rise"],
        )
    )
    assert assessment.limitations == ["what did the change history show"]
    assert assessment.unknowns == ["whether eviction preceded the latency rise"]


def test_representation_is_normalized_without_changing_content():
    assessment = admit_assessment(
        _proposal(
            candidates=[
                CandidateProposal(
                    statement="  a cause  ",
                    label="Weakly Supported",
                    supporting=[f" {MEMORY} ", ""],
                )
            ],
            next_check="  ",
        )
    )
    candidate = assessment.candidates[0]
    assert candidate.statement == "a cause"
    assert candidate.label is SupportLabel.WEAKLY_SUPPORTED
    assert candidate.supporting == [MEMORY]
    assert assessment.next_check is None


# --- what admission refuses, and it is only ever structure --------------------------------------
def test_a_string_no_grammar_could_produce_is_refused():
    """Not the same as a reference that does not resolve. This one names nothing under any prefix,
    so it would reach the resolver as a shape it has no branch for."""
    with pytest.raises(UnusableProposal, match="not a reference"):
        admit_assessment(_proposal(what_happened_refs=["evt-005-01"]))


def test_a_retired_reference_spelling_is_refused_as_structure():
    with pytest.raises(UnusableProposal):
        admit_assessment(_proposal(knowledge_used=["past_incident:inc-001"]))


def test_a_label_outside_the_vocabulary_is_refused_rather_than_defaulted():
    """Defaulting it would be choosing how well supported the candidate is, which is the model's
    statement to make and the gate's to check."""
    with pytest.raises(UnusableProposal, match="support labels"):
        admit_assessment(
            _proposal(candidates=[CandidateProposal(statement="c", label="quite likely")])
        )


def test_a_candidate_or_action_that_states_nothing_is_refused():
    with pytest.raises(UnusableProposal):
        admit_assessment(_proposal(candidates=[CandidateProposal(statement="  ", label="leading")]))
    with pytest.raises(UnusableProposal):
        admit_assessment(_proposal(actions=[ActionProposal(action="")]))


def test_an_unreadable_response_is_unusable_rather_than_a_thin_assessment():
    """Degrading would publish an assessment nothing proposed. Refusing leaves the caller free to
    spend a correction instead."""
    for text in ["", "I could not determine the cause.", "{not json at all"]:
        with pytest.raises(UnusableProposal):
            parse_proposal(text)


def test_a_fenced_json_response_is_read():
    proposal = parse_proposal('```json\n{"what_happened": "something broke"}\n```')
    assert proposal.what_happened == "something broke"


def test_the_unresolved_question_is_routing_metadata_and_not_assessment_content():
    proposal = parse_proposal(
        json.dumps(
            {
                "what_happened": "latency rose",
                "unknowns": ["whether the cache was the cause"],
                "unresolved_question": {
                    "question": "did the cache evict before the latency rose",
                    "evidence_kind": "metrics",
                },
            }
        )
    )
    assert proposal.unresolved_question is not None
    assert proposal.unresolved_question.evidence_kind == "metrics"
    assessment = admit_assessment(proposal)
    assert "unresolved_question" not in assessment.model_dump()
    assert assessment.unknowns == ["whether the cache was the cause"]


# --- the outcome follows from what the assessment holds -----------------------------------------
def test_no_established_candidate_is_inconclusive():
    assert outcome_of(Assessment()) is Outcome.INCONCLUSIVE
    assert outcome_of(Assessment(candidates=[_candidate("c", established=False)])) is (
        Outcome.INCONCLUSIVE
    )


def test_established_with_a_recorded_limitation_is_partial():
    assessment = Assessment(
        candidates=[_candidate("c", established=True)], limitations=["what changed"]
    )
    assert outcome_of(assessment) is Outcome.PARTIAL


def test_established_with_nothing_undisclosed_is_complete():
    assert outcome_of(Assessment(candidates=[_candidate("c", established=True)])) is (
        Outcome.COMPLETE
    )


# --- the brief renders what the assessment holds -------------------------------------------------
def test_the_brief_carries_the_outcome_and_no_probability():
    brief = render(admit_assessment(_proposal()))
    assert brief.outcome is Outcome.COMPLETE
    assert "Outcome: complete" in brief.text
    assert "%" not in brief.text
    assert "probab" not in brief.text.lower()


def test_the_brief_drops_nothing_the_assessment_holds():
    assessment = admit_assessment(
        _proposal(
            candidates=[
                CandidateProposal(
                    statement="the cache ceiling",
                    label="leading",
                    established=True,
                    supporting=[MEMORY],
                    weakening=[LOG],
                ),
                CandidateProposal(statement="a slow dependency", label="plausible"),
            ],
            unknowns=["whether eviction preceded the latency rise"],
            limitations=["what did the change history show"],
            next_check="compare the eviction and latency timestamps",
            history="this resembles an earlier eviction storm",
            history_refs=[RUNBOOK],
            knowledge_used=[RUNBOOK],
            actions=[ActionProposal(action="raise the memory ceiling", now=True)],
        )
    )
    text = render(assessment).text

    for statement in (c.statement for c in assessment.candidates):
        assert statement in text
    for reference in (MEMORY, LOG, RUNBOOK):
        assert reference in text
    assert "whether eviction preceded the latency rise" in text
    assert "what did the change history show" in text
    assert "compare the eviction and latency timestamps" in text
    assert "this resembles an earlier eviction storm" in text
    assert "raise the memory ceiling" in text


def test_weakening_evidence_is_never_dropped_from_the_brief():
    """A brief that drops a weakening observation asserts more than the assessment supports, which
    is the same defect as inventing a candidate."""
    assessment = admit_assessment(
        _proposal(
            candidates=[
                CandidateProposal(
                    statement="the cache ceiling",
                    label="leading",
                    established=True,
                    supporting=[MEMORY],
                    weakening=[LOG],
                )
            ]
        )
    )
    assert f"Weakens: {LOG}" in render(assessment).text


def test_the_brief_introduces_no_candidate_the_assessment_does_not_hold():
    assessment = admit_assessment(_proposal())
    text = render(assessment).text
    assert text.count("[leading, established]") == 1
    assert len([line for line in text.splitlines() if line.startswith("- ")]) == 1


def test_one_established_candidate_is_presented_as_the_leading_explanation():
    assessment = Assessment(candidates=[_candidate("the cache ceiling", established=True)])
    assert "What may be causing it" in render(assessment).text


def test_two_established_candidates_are_presented_as_contributing_causes():
    """Ranking co-causes would assert a structure the evidence did not produce."""
    assessment = Assessment(
        candidates=[
            _candidate("the cache ceiling", established=True),
            _candidate("the retry storm", established=True, label=SupportLabel.PLAUSIBLE),
        ]
    )
    text = render(assessment).text
    assert "Contributing causes" in text
    assert "What may be causing it" not in text


def test_an_affirmative_no_action_entry_renders_as_an_immediate_entry():
    """Never inferred from an empty list, and never quietly dropped for saying nothing to do."""
    assessment = Assessment(
        actions=[Action(action="no immediate action is required", now=True)],
    )
    assert "Now: no immediate action is required" in render(assessment).text


def test_an_action_says_whether_retrieved_guidance_supplied_it():
    assessment = Assessment(
        actions=[
            Action(action="follow the eviction runbook", now=True, knowledge_ref=RUNBOOK),
            Action(action="raise the memory ceiling", now=False),
        ]
    )
    text = render(assessment).text
    assert f"Now: follow the eviction runbook (guidance: {RUNBOOK})" in text
    assert "Later: raise the memory ceiling (own judgement)" in text


def test_the_brief_omits_what_the_assessment_left_empty():
    """Omitting an empty section is presentation. Omitting a populated one is not."""
    text = render(Assessment(what_happened="something happened")).text
    assert "What happened" in text
    assert "What history says" not in text
    assert "What to do" not in text


def test_rendering_is_deterministic():
    """No model call happens in rendering, so the same assessment renders identically every time."""
    assessment = admit_assessment(_proposal())
    assert render(assessment) == render(assessment)
