"""Deterministic sufficiency computation — the stop rule's inputs.

Code decides when the diagnosis loop may stop, not model confidence. Sufficiency is computed each
turn over the *gathered* evidence (the full observation trail, not just what the hypothesis cites),
scaled by severity:

- SEV1: requires all four core classes — logs + metrics + dependency-impact + a recent-change check.
- SEV2: requires >= 2 independent evidence classes.
- SEV3 / SEV4: requires >= 1.

Evidence class is read from the frozen ref grammar prefix (`logs:` / `metrics:` / `deps:` /
`deploys:` / ...), so gathering a tool's results counts toward coverage even when the deterministic
hypothesis does not cite them (the LLM will).
"""

from __future__ import annotations

from collections.abc import Iterable

from opspilot.diagnosis.contracts import Hypothesis, SufficiencyState

SEV1_REQUIRED = ("logs", "metrics", "deps", "deploys")  # deploys stands in for "recent change"


def evidence_class(ref: str) -> str:
    """The evidence class of a ref is its grammar prefix (`deploys:svc:id` -> `deploys`)."""
    return ref.split(":", 1)[0]


def _coverage(severity: str, gathered: set[str]) -> tuple[float, list[str]]:
    if severity == "SEV1":
        required = list(SEV1_REQUIRED)
        return len(gathered & set(required)) / len(required), required
    if severity == "SEV2":
        return min(len(gathered), 2) / 2, [">=2 independent evidence classes"]
    return min(len(gathered), 1) / 1, [">=1 evidence class"]  # SEV3 / SEV4 / default


def compute_sufficiency(
    severity: str | None,
    produced_refs: Iterable[str],
    hypothesis: Hypothesis | None,
    plan_can_advance: bool,
) -> SufficiencyState:
    produced = set(produced_refs)
    gathered = {evidence_class(r) for r in produced}
    coverage, required = _coverage(severity or "SEV3", gathered)

    cited = [c.ref for c in hypothesis.citations] if hypothesis else []
    citation_coverage = 1.0 if not cited else sum(r in produced for r in cited) / len(cited)

    return SufficiencyState(
        evidence_classes=sorted(gathered),
        required_classes=required,
        evidence_coverage=round(coverage, 4),
        citation_coverage=round(citation_coverage, 4),
        # The deterministic slice does not detect contradictions or track critical-question gaps;
        # these dimensions exist for the LLM loop to populate. Kept at 0 so they never block here.
        contradictions_unresolved=0,
        unresolved_critical_questions=0,
        plan_can_advance=plan_can_advance,
    )
