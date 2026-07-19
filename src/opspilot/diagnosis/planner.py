"""Planner seam — the single point where a model plugs into the frozen diagnosis loop.

Stage 4a introduces the seam with the deterministic planner behind it (no behavior change);
Stage 4b adds the LLM planner. `run_cycle`'s execution transitions, the tool envelope, the
read-only registry, and the sufficiency gate are all unchanged — only *which diagnostic questions
to pursue next* moves behind this interface. Hypothesis synthesis stays inside `run_cycle` for now;
making it model-driven (with the matching `run_cycle` split) lands in 4b, when the LLM updater is
the real consumer.

The deterministic planner is retained as the fallback tier and the eval floor
(`evaluate(implementation="deterministic")`) that the single-agent implementation must beat.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from opspilot.diagnosis.cycle import plan_investigation

if TYPE_CHECKING:
    from opspilot.diagnosis.contracts import (
        DiagnosisContext,
        Hypothesis,
        InvestigationPlan,
        ToolObservation,
    )
    from opspilot.llm.base import ChatModel


@runtime_checkable
class Planner(Protocol):
    """Chooses which `DiagnosticQuestion`s to pursue next.

    Deterministic today; model-driven in 4b. `answered` and `observations` are the loop state a
    model planner needs to pick the next question adaptively — the deterministic planner ignores
    them (it emits the full static plan and `run_cycle` skips already-answered questions).
    """

    name: str

    def plan(
        self,
        ctx: DiagnosisContext,
        *,
        answered: set[str],
        observations: list[ToolObservation],
    ) -> InvestigationPlan: ...

    def revise_hypothesis(
        self,
        base: Hypothesis,
        *,
        ctx: DiagnosisContext | None = None,
        produced_refs: set[str] | None = None,
        observations: list[ToolObservation] | None = None,
        final: bool = False,
    ) -> Hypothesis:
        """Revise the run_cycle hypothesis from the evidence gathered so far. On the stopping turn
        (`final`) a model planner synthesizes its grounded conclusion from `observations`; any
        citation must be in `produced_refs`. The deterministic planner returns `base` unchanged.
        """
        ...

    def wants_to_continue(self, plan: InvestigationPlan, *, answered: set[str]) -> bool:
        """Whether the loop should take another turn (subject to sufficiency + budget). The
        deterministic planner front-loads its questions, so it stops once they are all answered; the
        LLM planner proposes one step at a time, so it continues while it is still proposing steps.
        """
        ...


class DeterministicPlanner:
    """The frozen deployment-regression plan (+ counter-evidence) — the Stage-4 floor.

    Delegates to `plan_investigation` and deliberately ignores `answered`/`observations`, so the
    plan handed to `run_cycle` is identical to calling `plan_investigation(ctx)` directly. This is
    what keeps 4a a no-behavior-change seam: the committed scorecard stays byte-identical.
    """

    name = "deterministic"

    def plan(
        self,
        ctx: DiagnosisContext,
        *,
        answered: set[str] | None = None,
        observations: list[ToolObservation] | None = None,
    ) -> InvestigationPlan:
        return plan_investigation(ctx)

    def revise_hypothesis(
        self,
        base: Hypothesis,
        *,
        ctx: DiagnosisContext | None = None,
        produced_refs: set[str] | None = None,
        observations: list[ToolObservation] | None = None,
        final: bool = False,
    ) -> Hypothesis:
        """No-op: the deterministic hypothesis is exactly what run_cycle formed."""
        return base

    def wants_to_continue(self, plan: InvestigationPlan, *, answered: set[str]) -> bool:
        """Continue while the front-loaded plan still has unanswered questions (original rule)."""
        return bool({q.key for q in plan.questions} - answered)


# The diagnosis implementations selectable via `evaluate(implementation=...)`. The deterministic
# floor is the default and the eval baseline; `single_agent` is the LLM planner (4b).
KNOWN_IMPLEMENTATIONS = ("deterministic", "single_agent")


def build_planner(
    implementation: str = "deterministic", *, model: ChatModel | None = None
) -> Planner:
    """Construct the planner for an implementation label; unknown -> ValueError (fail loud).

    `single_agent` builds an `LLMPlanner`; `model` overrides the configured chat model (the eval
    passes a cassette-backed replay model so the scorecard is deterministic in CI).
    """
    if implementation == "deterministic":
        return DeterministicPlanner()
    if implementation == "single_agent":
        from opspilot.diagnosis.llm_planner import LLMPlanner
        from opspilot.llm.client import build_chat_model

        return LLMPlanner(model or build_chat_model())
    known = ", ".join(KNOWN_IMPLEMENTATIONS)
    raise ValueError(f"unknown diagnosis implementation {implementation!r}; known: {known}")
