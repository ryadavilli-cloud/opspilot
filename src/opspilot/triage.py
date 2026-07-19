"""Triage seam — classify an incident behind one interface (deterministic floor / LLM at 4c).

Data extraction (the incident record, alert storm, affected services, onset, severity, category)
stays in the `triage_router` node. Only the *classification* moves here: known-issue-vs-novel and
which past postmortem is the recurrence candidate. The deterministic triager can match an incident
only to its OWN postmortem; the LLM triager reasons over the surfaced past-incident candidates and
can spot a genuine recurrence (inc-007 -> inc-003) — the "candidate" half of Stage 9's
candidate+verify (the deterministic verification of that candidate lands in Stage 9).

Fail-closed: a malformed or over-confident model response falls back to `novel_investigation` (full
investigation), never a fabricated known-issue match that would shortcut to a stored resolution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from opspilot.llm.prompts import get_prompt
from opspilot.state import Intent

if TYPE_CHECKING:
    from opspilot.llm.base import ChatModel

_VALID_INTENTS = {
    Intent.KNOWN_ISSUE.value,
    Intent.NOVEL_INVESTIGATION.value,
    Intent.INFO_ONLY.value,
}


class PastCandidate(BaseModel):
    doc_id: str      # a postmortem ref, e.g. postmortem:inc-003
    title: str = ""


class TriageContext(BaseModel):
    incident_id: str
    short_description: str = ""
    category: str = ""
    affected_services: list[str] = Field(default_factory=list)
    alert_signals: list[str] = Field(default_factory=list)
    past_candidates: list[PastCandidate] = Field(default_factory=list)

    def candidate_ids(self) -> set[str]:
        return {c.doc_id for c in self.past_candidates}


class TriageDecision(BaseModel):
    intent: str
    matched_incident: str = ""


@runtime_checkable
class Triager(Protocol):
    """Classifies an incident's intent + known-issue candidate. Deterministic floor / LLM at 4c."""

    name: str

    def classify(self, ctx: TriageContext) -> TriageDecision: ...


class DeterministicTriager:
    """Exact self-match: known-issue only if the incident's OWN postmortem is a candidate. This is
    the frozen baseline — the routing the LLM triager must beat (it misses genuine recurrences)."""

    name = "deterministic"

    def classify(self, ctx: TriageContext) -> TriageDecision:
        own = f"postmortem:{ctx.incident_id}"
        matched = own if own in ctx.candidate_ids() else ""
        intent = Intent.KNOWN_ISSUE.value if matched else Intent.NOVEL_INVESTIGATION.value
        return TriageDecision(intent=intent, matched_incident=matched)


def _render_context(ctx: TriageContext) -> str:
    services = ", ".join(ctx.affected_services) or "(unknown)"
    signals = "; ".join(ctx.alert_signals) or "(none)"
    return (
        f"- incident_id: {ctx.incident_id}\n"
        f"- description: {ctx.short_description or '(none)'}\n"
        f"- category: {ctx.category or '(unknown)'}\n"
        f"- affected services: {services}\n"
        f"- alert signals: {signals}"
    )


def _render_candidates(ctx: TriageContext) -> str:
    if not ctx.past_candidates:
        return "(no similar past incidents found)"
    return "\n".join(f"- {c.doc_id}: {c.title}" for c in ctx.past_candidates)


class LLMTriager:
    """A `Triager` that asks a model to classify intent + the recurrence candidate."""

    name = "single_agent"

    def __init__(self, model: ChatModel, *, prompt_name: str = "triage") -> None:
        self._model = model
        self._prompt = get_prompt(prompt_name)
        self.prompt_version = self._prompt.version

    def classify(self, ctx: TriageContext) -> TriageDecision:
        from opspilot.diagnosis.llm_planner import extract_json_object
        from opspilot.llm.base import ChatMessage

        rendered = self._prompt.text.replace(
            "{incident}", _render_context(ctx)
        ).replace("{candidates}", _render_candidates(ctx))
        try:
            response = self._model.complete([ChatMessage(role="user", content=rendered)])
            decision = extract_json_object(response.text)
        except ValueError:
            return TriageDecision(intent=Intent.NOVEL_INVESTIGATION.value)  # fail closed

        intent = str(decision.get("intent", "")).strip()
        if intent not in _VALID_INTENTS:
            return TriageDecision(intent=Intent.NOVEL_INVESTIGATION.value)
        if intent != Intent.KNOWN_ISSUE.value:
            return TriageDecision(intent=intent)  # info_only / novel carry no match

        # known_issue must name a REAL candidate — reject a hallucination, fail closed to novel.
        matched = str(decision.get("matched_incident") or "").strip()
        if matched not in ctx.candidate_ids():
            return TriageDecision(intent=Intent.NOVEL_INVESTIGATION.value)
        return TriageDecision(intent=intent, matched_incident=matched)


KNOWN_IMPLEMENTATIONS = ("deterministic", "single_agent")


def build_triager(
    implementation: str = "deterministic", *, model: ChatModel | None = None
) -> Triager:
    """Construct the triager for an implementation label; unknown -> ValueError (fail loud)."""
    if implementation == "deterministic":
        return DeterministicTriager()
    if implementation == "single_agent":
        from opspilot.llm.client import build_chat_model

        return LLMTriager(model or build_chat_model())
    known = ", ".join(KNOWN_IMPLEMENTATIONS)
    raise ValueError(f"unknown triage implementation {implementation!r}; known: {known}")
