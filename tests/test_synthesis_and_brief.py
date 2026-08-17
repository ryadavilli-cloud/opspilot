"""Synthesis admission and the brief projection.

The model proposes; code admits. These assert the refusals, because the refusals are what stop a
model's assertion from becoming a published structure nothing verified. The brief tests assert the
symmetric rule: a rendering may not add what the assessment lacks, and may not drop what it holds.
"""

from __future__ import annotations

from opspilot.assessment.brief import project
from opspilot.assessment.contracts import (
    BRIEF_SECTIONS,
    ConclusionDisposition,
    Horizon,
    RecommendationKind,
    RecommendationProvenance,
    Strength,
    SupportLabel,
)
from opspilot.assessment.synthesis import (
    AssessmentProposal,
    CandidateProposal,
    RecommendationProposal,
    admit_assessment,
    parse_proposal,
)
from opspilot.evidence.admission import AdmittedObservation, EvidenceType, Limitation
from opspilot.tools.contracts import Completeness, ExecutionOutcome

MEMORY = "metrics:redis-cache:used_memory_pct@2026-06-22T11:35:00Z"
EVICTED = "metrics:redis-cache:evicted_keys_rate@2026-06-22T11:40:00Z"
LOG = "logs:checkout-api:evt-005-01"
UNADMITTED = "logs:payment-api:evt-999-99"


def _observation(
    ref: str,
    completeness: Completeness = Completeness.COMPLETE,
    *,
    operation_ref: str = "op-0001",
) -> AdmittedObservation:
    return AdmittedObservation(
        evidence_ref=ref,
        investigation_id="inv-1",
        operation_ref=operation_ref,
        evidence_type=EvidenceType.METRIC,
        source="get_metrics",
        completeness=completeness,
        observation={"value": 99.0},
        provenance="get_metrics(service=redis-cache)",
        # What admission attaches to a partial observation, and the words the disclosure carries.
        limitations=(
            ("the source returned part of the requested scope",)
            if completeness is Completeness.PARTIAL
            else ()
        ),
    )


def _limitation() -> Limitation:
    return Limitation(
        question="what did the change history show",
        reason="the source could not be reached",
        operation_ref="op-0002",
        capability="get_deployments",
        outcome=ExecutionOutcome.UNAVAILABLE,
    )


def _admit(
    proposal: AssessmentProposal, refs=(MEMORY, EVICTED, LOG), limitations=(), *, partial=()
):
    return admit_assessment(
        proposal,
        investigation_id="inv-1",
        turn_id="turn-1",
        objective="explain the checkout latency rise",
        observations=[
            _observation(r, Completeness.PARTIAL if r in partial else Completeness.COMPLETE)
            for r in refs
        ],
        limitations=list(limitations),
    )


def _full_proposal() -> AssessmentProposal:
    return AssessmentProposal(
        what_happened="checkout latency rose while the cache evicted keys",
        what_happened_refs=[LOG],
        leading=CandidateProposal(
            statement="redis-cache hit its memory ceiling and evicted session keys",
            supporting_refs=[MEMORY, EVICTED],
        ),
        recommendations=[
            RecommendationProposal(
                action="raise the cache memory ceiling",
                horizon="now",
                kind="mitigation",
                responds_to="the leading candidate",
                confirm_signal="eviction rate returns to zero",
            )
        ],
    )


# --- what admission refuses ---------------------------------------------------------------------
def test_a_reference_the_turn_never_admitted_is_dropped():
    """The model may name anything. Only what admission produced can be cited."""
    proposal = _full_proposal()
    proposal = proposal.model_copy(
        update={
            "leading": CandidateProposal(
                statement="cache ceiling", supporting_refs=[MEMORY, UNADMITTED]
            )
        }
    )
    assessment = _admit(proposal)
    assert assessment.leading_candidate is not None
    assert assessment.leading_candidate.supporting == [MEMORY]


def test_a_candidate_with_no_admitted_support_is_dropped_entirely():
    """A candidate resting on nothing this turn observed is not an explanation of it, so it is
    removed rather than published with an empty support list."""
    proposal = AssessmentProposal(
        leading=CandidateProposal(statement="invented cause", supporting_refs=[UNADMITTED])
    )
    assessment = _admit(proposal)
    assert assessment.leading_candidate is None
    assert assessment.disposition is ConclusionDisposition.INSUFFICIENT_EVIDENCE


def test_the_disposition_follows_the_evidence_not_the_model():
    """Nothing the model says about its own certainty can turn insufficiency into a conclusion."""
    grounded = _admit(_full_proposal())
    assert grounded.disposition is ConclusionDisposition.SUPPORTED_CONCLUSION

    ungrounded = _admit(_full_proposal(), refs=())
    assert ungrounded.disposition is ConclusionDisposition.INSUFFICIENT_EVIDENCE
    assert ungrounded.leading_candidate is None


def test_what_happened_is_established_only_with_admitted_support():
    with_support = _admit(_full_proposal())
    assert with_support.what_happened.strength is Strength.ESTABLISHED

    proposal = _full_proposal().model_copy(update={"what_happened_refs": [UNADMITTED]})
    without = _admit(proposal)
    assert without.what_happened.strength is Strength.POSSIBLE
    assert without.what_happened.citations == []


def test_alternatives_are_never_promoted_above_possible():
    proposal = _full_proposal().model_copy(
        update={
            "alternatives": [
                CandidateProposal(statement="a slow dependency", supporting_refs=[LOG])
            ]
        }
    )
    assessment = _admit(proposal)
    assert assessment.supported_alternatives[0].strength is Strength.POSSIBLE
    assert assessment.supported_alternatives[0].label is SupportLabel.PLAUSIBLE


def test_recommendations_are_labelled_model_generated_when_no_retrieval_ran():
    """Nothing here can be attributed to a runbook, because no retrieval ran. Saying so is the
    honest form, and it is what keeps a plausible suggestion from looking sourced."""
    assessment = _admit(_full_proposal())
    rec = assessment.recommendations[0]
    assert rec.provenance is RecommendationProvenance.GENERAL_PRACTICE
    assert rec.knowledge_reference is None


def test_a_mitigation_without_a_confirm_signal_becomes_a_verification_step():
    """Rather than refusing the whole recommendation: the action is still useful, it just is not a
    mitigation if nothing would show it worked."""
    proposal = AssessmentProposal(
        recommendations=[
            RecommendationProposal(action="restart the cache", horizon="now", kind="mitigation")
        ]
    )
    assessment = _admit(proposal)
    assert assessment.recommendations[0].kind is RecommendationKind.VERIFICATION


def test_an_unknown_horizon_or_kind_falls_back_rather_than_failing_the_turn():
    proposal = AssessmentProposal(
        recommendations=[
            RecommendationProposal(action="do something", horizon="immediately", kind="fix-it")
        ]
    )
    rec = _admit(proposal).recommendations[0]
    assert rec.horizon is Horizon.SOON and rec.kind is RecommendationKind.VERIFICATION


def test_limitations_travel_from_admission_into_the_assessment():
    assessment = _admit(_full_proposal(), limitations=[_limitation()])
    assert len(assessment.limitations) == 1
    assert assessment.limitations[0].outcome is ExecutionOutcome.UNAVAILABLE


# --- a partial observation stays marked partial where a claim rests on it ------------------------
def test_a_claim_resting_on_a_partial_observation_discloses_what_it_did_not_see():
    """The unseen remainder could change the picture, so an element resting on a capped read must
    say so. Without this the assessment reads as though the whole scope was observed, which is the
    one reading a partial observation must never support."""
    assessment = _admit(_full_proposal(), partial=(MEMORY,))

    disclosures = [lim for lim in assessment.limitations if lim.operation_ref == "op-0001"]
    assert disclosures, "a cited partial observation disclosed nothing"
    assert "did not return" in disclosures[0].question
    assert "part of the requested scope" in disclosures[0].reason


def test_an_incompleteness_disclosure_stays_distinguishable_from_a_source_that_did_not_answer():
    """Both are limitations, and they mean different things: one source answered incompletely, the
    other did not answer. The execution outcome is what tells them apart, so it must not be
    flattened onto a single failure value."""
    assessment = _admit(_full_proposal(), limitations=[_limitation()], partial=(MEMORY,))

    outcomes = {lim.capability: lim.outcome for lim in assessment.limitations}
    assert outcomes["get_deployments"] is ExecutionOutcome.UNAVAILABLE  # did not answer
    assert outcomes["get_metrics"] is ExecutionOutcome.SUCCEEDED  # answered, but not in full


def test_a_complete_observation_discloses_nothing():
    """A false disclosure is its own defect: it would understate evidence the turn fully saw."""
    assessment = _admit(_full_proposal())
    assert assessment.limitations == []


def test_a_partial_observation_no_claim_rests_on_is_not_disclosed_as_a_gap_in_a_claim():
    """LOG is admitted partial but the proposal below cites only the two metrics. The assessment
    makes no claim on it, so there is no claim whose completeness is in question."""
    proposal = _full_proposal().model_copy(update={"what_happened_refs": [MEMORY]})
    assessment = _admit(proposal, partial=(LOG,))
    assert assessment.limitations == []


def test_several_references_capped_by_one_read_disclose_once():
    """MEMORY and EVICTED come from the same operation. Two disclosures would read as two separate
    incomplete answers when there was one."""
    assessment = _admit(_full_proposal(), partial=(MEMORY, EVICTED))
    assert len([lim for lim in assessment.limitations if lim.operation_ref == "op-0001"]) == 1


def test_the_incompleteness_disclosure_reaches_the_brief():
    """The brief renders the assessment and introduces nothing it does not contain, so a
    disclosure that stopped at the assessment would never reach the engineer who has to weigh it."""
    brief = project(_admit(_full_proposal(), partial=(MEMORY,)))
    body = "\n".join(section.body for section in brief.sections)
    assert "part of the requested scope" in body


# --- parsing the model's response ----------------------------------------------------------------
def test_a_fenced_json_response_is_read():
    proposal = parse_proposal('```json\n{"what_happened": "something broke"}\n```')
    assert proposal.what_happened == "something broke"


def test_an_unreadable_response_degrades_rather_than_raising():
    """Losing the whole turn because the model wrote prose would discard the evidence the turn did
    gather. A thin assessment that establishes nothing is the truthful result."""
    for text in ["", "I could not determine the cause.", "{not json at all"]:
        assessment = _admit(parse_proposal(text))
        assert assessment.leading_candidate is None
        assert assessment.disposition is ConclusionDisposition.INSUFFICIENT_EVIDENCE


# --- the brief renders what the assessment holds -------------------------------------------------
def test_the_brief_leads_with_the_conclusion_and_next_action():
    brief = project(_admit(_full_proposal()))
    lead = brief.sections[0]
    assert lead.name == "current_conclusion_and_next_action"
    assert "memory ceiling" in lead.body
    assert "Next action:" in lead.body


def test_an_inconclusive_brief_says_so_rather_than_presenting_a_best_guess():
    proposal = AssessmentProposal(
        leading=CandidateProposal(statement="a guess", supporting_refs=[UNADMITTED]),
        unresolved_discriminator="whether eviction preceded the latency rise",
    )
    brief = project(_admit(proposal))
    assert "does not support stating a cause" in brief.sections[0].body
    assert "whether eviction preceded" in brief.sections[0].body


def test_weakening_evidence_is_never_dropped_from_the_brief():
    """A brief that drops a weakening observation asserts more than the assessment supports, which
    is the same defect as inventing a candidate."""
    proposal = _full_proposal().model_copy(
        update={
            "leading": CandidateProposal(
                statement="cache ceiling", supporting_refs=[MEMORY], weakening_refs=[LOG]
            )
        }
    )
    brief = project(_admit(proposal))
    evidence = next(s for s in brief.sections if s.name == "supporting_and_weakening_evidence")
    assert f"weakens [leading]: {LOG}" in evidence.body


def test_every_recorded_limitation_reaches_the_brief():
    brief = project(_admit(_full_proposal(), limitations=[_limitation()]))
    unknown = next(s for s in brief.sections if s.name == "what_remains_unknown")
    assert "what did the change history show" in unknown.body


def test_the_brief_omits_sections_the_assessment_left_empty():
    """Omitting an empty section is presentation. Omitting a populated one is not."""
    brief = project(_admit(AssessmentProposal(what_happened="something happened")))
    names = {s.name for s in brief.sections}
    assert "what_history_says" not in names
    assert "what_to_do" not in names
    assert "what_happened" in names


def test_brief_sections_are_a_subset_of_the_accepted_eight_in_order():
    brief = project(_admit(_full_proposal(), limitations=[_limitation()]))
    names = [s.name for s in brief.sections]
    assert set(names) <= set(BRIEF_SECTIONS)
    assert names == sorted(names, key=BRIEF_SECTIONS.index)


def test_the_brief_introduces_no_candidate_the_assessment_does_not_hold():
    assessment = _admit(_full_proposal())
    brief = project(assessment)
    causes = next(s for s in brief.sections if s.name == "what_may_be_causing_it")
    assert causes.body.count("\n") + 1 == len(assessment.candidates())


def test_projection_is_deterministic():
    """No model call happens in rendering, so the same assessment renders identically every time."""
    assessment = _admit(_full_proposal(), limitations=[_limitation()])
    assert project(assessment) == project(assessment)
