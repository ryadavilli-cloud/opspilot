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
        InvestigationPlan,
        ToolObservation,
    )


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


# Registry of available diagnosis implementations, keyed by the `evaluate(implementation=...)`
# label. `single_agent` (the LLM planner) registers here in 4b; until then, asking for it fails
# loudly rather than silently falling back to the deterministic floor and mislabeling the run.
PLANNERS: dict[str, type[Planner]] = {
    "deterministic": DeterministicPlanner,
}


def build_planner(implementation: str = "deterministic") -> Planner:
    """Construct the planner for an implementation label; unknown -> ValueError (fail loud)."""
    try:
        return PLANNERS[implementation]()
    except KeyError:
        known = ", ".join(sorted(PLANNERS))
        raise ValueError(
            f"unknown diagnosis implementation {implementation!r}; known: {known}"
        ) from None
