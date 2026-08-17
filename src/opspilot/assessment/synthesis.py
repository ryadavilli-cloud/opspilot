"""Synthesis: the model proposes an assessment, code admits its structure.

The proposal arrives as loose strings, because a model cannot be trusted to satisfy a closed
vocabulary or to name a reference that exists. What happens here is structural and nothing more:
read the JSON, enforce the field types, normalize harmless representation, and refuse a proposal
whose structure cannot be used or that names a string no reference grammar could ever produce.

What this deliberately does not do is judge. It does not remove a candidate whose support was
never admitted, does not derive or downgrade `established`, and does not discard an action for its
provenance. Every one of those is a claim about whether the evidence bears out what was proposed,
and grounding is the single owner of that question. A filter here would answer it first, quietly,
and the gate would then approve an assessment it never actually saw.

Refusal is still available, and it is structural: a response that is not a readable proposal, or
that carries a reference string the grammar cannot parse, is unusable rather than thin. The caller
decides what an unusable proposal costs.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError, model_validator

from opspilot.assessment.contracts import Action, Assessment, Candidate, SupportLabel
from opspilot.evidence.references import try_parse

SYNTHESIS_TASK = "rca_synthesis"

# Label text as the model may write it, mapped to the one vocabulary. Case and separator variation
# is representation; a word outside the three is not, and is refused rather than defaulted.
_LABELS = {label.value: label for label in SupportLabel}


class UnusableProposal(ValueError):
    """A model response that cannot become an assessment: unreadable, structurally invalid, or
    naming a string that could not be a reference under any grammar. Raised rather than degraded,
    so the caller can spend a correction instead of publishing something nothing proposed."""


class _Proposed(BaseModel):
    """A shape the model writes, where a field it has nothing for may arrive as `null`.

    Several of these fields are optional, and `null` is how JSON says a value is absent. The
    defaults below already say the same thing, so the two encodings are read as one. Refusing the
    whole proposal over the difference would discard a complete assessment for a punctuation
    choice, and refusal is meant for output nothing can be made of.
    """

    @model_validator(mode="before")
    @classmethod
    def _null_means_absent(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {key: value for key, value in data.items() if value is not None}
        return data


class CandidateProposal(_Proposed):
    statement: str = ""
    label: str = ""
    established: bool = False
    supporting: list[str] = Field(default_factory=list)
    weakening: list[str] = Field(default_factory=list)


class ActionProposal(_Proposed):
    action: str = ""
    now: bool = False
    knowledge_ref: str = ""


class UnresolvedQuestion(_Proposed):
    """What remains unanswered and the kind of evidence that could answer it.

    Routing metadata only: the same matter is stated in `unknowns`, so the assessment is complete
    whether or not anything acts on this.
    """

    question: str = ""
    evidence_kind: str = ""


class AssessmentProposal(_Proposed):
    """The assessment's shape as the model offers it: loose strings, plus the one routing field."""

    what_happened: str = ""
    what_happened_refs: list[str] = Field(default_factory=list)
    candidates: list[CandidateProposal] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    next_check: str = ""
    actions: list[ActionProposal] = Field(default_factory=list)
    history: str = ""
    history_refs: list[str] = Field(default_factory=list)
    knowledge_used: list[str] = Field(default_factory=list)
    unresolved_question: UnresolvedQuestion | None = None


def parse_proposal(text: str) -> AssessmentProposal:
    """Read the model's JSON, tolerating the fencing and prose models wrap it in."""
    cleaned = (text or "").strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise UnusableProposal("the response carries no JSON object")
    try:
        return AssessmentProposal.model_validate(json.loads(cleaned[start : end + 1]))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise UnusableProposal(f"the proposal is not the expected structure: {exc}") from exc


def _texts(values: list[str]) -> list[str]:
    """Strip and drop blanks. Whitespace and empty entries are representation, not content."""
    return [stripped for value in values if (stripped := value.strip())]


def _references(values: list[str], where: str) -> list[str]:
    """The same, plus the one grammar check. A string no prefix can claim is not a reference that
    failed to resolve; it could never name anything, and admitting it would carry a shape the
    resolver has no branch for into the gate."""
    refs = _texts(values)
    for ref in refs:
        if try_parse(ref) is None:
            raise UnusableProposal(f"{ref!r} in {where} is not a reference")
    return refs


def _label(text: str) -> SupportLabel:
    normalized = text.strip().lower().replace(" ", "_").replace("-", "_")
    label = _LABELS.get(normalized)
    if label is None:
        raise UnusableProposal(f"{text!r} is not one of the support labels")
    return label


def _candidate(proposal: CandidateProposal, position: int) -> Candidate:
    statement = proposal.statement.strip()
    if not statement:
        raise UnusableProposal(f"candidate {position} states nothing")
    return Candidate(
        statement=statement,
        label=_label(proposal.label),
        established=proposal.established,
        supporting=_references(proposal.supporting, f"candidate {position} support"),
        weakening=_references(proposal.weakening, f"candidate {position} weakening"),
    )


def _action(proposal: ActionProposal, position: int) -> Action:
    action = proposal.action.strip()
    if not action:
        raise UnusableProposal(f"action {position} says nothing to do")
    reference = proposal.knowledge_ref.strip()
    if reference and try_parse(reference) is None:
        raise UnusableProposal(f"{reference!r} on action {position} is not a reference")
    return Action(action=action, now=proposal.now, knowledge_ref=reference or None)


def admit_assessment(proposal: AssessmentProposal) -> Assessment:
    """Convert a parsed proposal into the assessment. Structure only: what the model proposed is
    what the grounding gate sees."""
    history = proposal.history.strip()
    return Assessment(
        what_happened=proposal.what_happened.strip(),
        what_happened_refs=_references(proposal.what_happened_refs, "what_happened"),
        candidates=[
            _candidate(candidate, position)
            for position, candidate in enumerate(proposal.candidates, start=1)
        ],
        unknowns=_texts(proposal.unknowns),
        limitations=_texts(proposal.limitations),
        next_check=proposal.next_check.strip() or None,
        actions=[
            _action(action, position) for position, action in enumerate(proposal.actions, start=1)
        ],
        history=history or None,
        history_refs=_references(proposal.history_refs, "history"),
        knowledge_used=_references(proposal.knowledge_used, "knowledge_used"),
    )
