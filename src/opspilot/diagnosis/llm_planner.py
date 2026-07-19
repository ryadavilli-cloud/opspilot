"""LLM-driven planner (Stage 4b) — the model chooses the next diagnostic tool call.

Plugs into the same `Planner` seam as the deterministic floor: `run_cycle`'s execution, the tool
envelope, the read-only registry, and the sufficiency gate are unchanged. Only *which question to
pursue next* is model-driven here (root-cause synthesis is the deterministic floor for now and
becomes model-driven in the hypothesis-split step).

Fail-closed: a response that selects a non-allowlisted (e.g. mutating) tool, or that cannot be
parsed, yields no question — the loop then advances to escalate via the budget / plan-can-advance
rules rather than executing an unvetted call. The read-only registry is the hard boundary; the
prompt is not trusted to respect it.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from opspilot.config import MAX_DIAGNOSE_ITERS
from opspilot.diagnosis.contracts import (
    DiagnosticQuestion,
    EvidenceCitation,
    Hypothesis,
    InvestigationPlan,
    ToolCallRequest,
)
from opspilot.guardrails.policies import is_read_only
from opspilot.llm.prompts import get_prompt

if TYPE_CHECKING:
    from opspilot.diagnosis.contracts import DiagnosisContext, ToolObservation
    from opspilot.llm.base import ChatModel

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)

# Tool params that are lists; the model often returns a bare scalar (e.g. services: "checkout-api").
# We coerce scalar -> [scalar] for exactly these, rather than trusting the model to match shapes.
_LIST_PARAMS: dict[str, set[str]] = {"get_deployments": {"services"}}


def extract_json_object(text: str) -> dict:
    """Pull the decision JSON out of a model response. Tolerates `<think>…</think>` preambles
    (qwen3) and ```json fences; falls back to the outermost brace span. Raises ValueError if none
    parses, so the caller can fail closed."""
    cleaned = _THINK_RE.sub("", text).strip()
    fence = _FENCE_RE.search(cleaned)
    if fence:
        cleaned = fence.group(1)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError(f"no parseable JSON object in model response: {text[:200]!r}")


def _params_key(params: dict) -> str:
    """Stable key fragment so a re-entered loop dedups repeat calls (never re-asks)."""
    return json.dumps(params, sort_keys=True, separators=(",", ":"))


def _coerce_params(tool: str, params: dict) -> dict:
    """Coerce known scalar-vs-list param mismatches to the tool's shape. Models return list params
    as a bare scalar or a comma-joined string (e.g. services: "a,b"); normalize both to a list."""
    list_params = _LIST_PARAMS.get(tool, set())
    out: dict = {}
    for key, value in params.items():
        if key in list_params and isinstance(value, str):
            value = [part.strip() for part in value.split(",") if part.strip()]
        elif key in list_params and not isinstance(value, list):
            value = [value]
        out[key] = value
    return out


def _render_context(ctx: DiagnosisContext) -> str:
    services = ", ".join(ctx.affected_services) or "(unknown)"
    return (
        f"- incident_id: {ctx.incident_id}\n"
        f"- category: {ctx.category or '(unknown)'}\n"
        f"- affected services: {services}\n"
        f"- symptom onset: {ctx.onset or '(unknown)'}"
    )


def _render_observations(observations: list[ToolObservation]) -> str:
    if not observations:
        return "Nothing yet — this is your first step."
    lines = []
    tools_called: set[str] = set()
    classes: set[str] = set()
    for obs in observations:
        refs = ", ".join(obs.evidence_refs) or "(no evidence refs)"
        lines.append(
            f"- {obs.tool} [{obs.status}] → {obs.result_count} result(s); refs: {refs}"
        )
        tools_called.add(obs.tool)
        classes.update(ref.split(":", 1)[0] for ref in obs.evidence_refs)
    summary = (
        f"\nTools already called (do NOT call these again): {', '.join(sorted(tools_called))}."
        f"\nEvidence classes gathered so far: {', '.join(sorted(classes)) or 'none'}. "
        "Gather a different class (deploys / logs / metrics / deps) or conclude with `done`."
    )
    return "\n".join(lines) + summary


class LLMPlanner:
    """A `Planner` that asks a model for the next read-only tool call."""

    name = "single_agent"

    def __init__(
        self,
        model: ChatModel,
        *,
        prompt_name: str = "diagnose_planner",
        synthesis_prompt: str = "diagnose_synthesize",
    ) -> None:
        self._model = model
        self._prompt = get_prompt(prompt_name)
        self._synth_prompt = get_prompt(synthesis_prompt)
        self.prompt_version = self._prompt.version
        self.last_decision: dict | None = None

    def plan(
        self,
        ctx: DiagnosisContext,
        *,
        answered: set[str],
        observations: list[ToolObservation],
    ) -> InvestigationPlan:
        from opspilot.llm.base import ChatMessage

        # str.replace (not str.format): the prompt embeds literal JSON braces in its examples.
        rendered = self._prompt.text.replace(
            "{incident_context}", _render_context(ctx)
        ).replace("{observations}", _render_observations(observations))

        result = self._model.complete([ChatMessage(role="user", content=rendered)])
        try:
            decision = extract_json_object(result.text)
        except ValueError:
            self.last_decision = None
            return InvestigationPlan(max_iters=MAX_DIAGNOSE_ITERS, questions=[])
        self.last_decision = decision

        if decision.get("done"):
            return InvestigationPlan(max_iters=MAX_DIAGNOSE_ITERS, questions=[])

        tool = str(decision.get("next_tool", ""))
        params = decision.get("params") or {}
        if not isinstance(params, dict) or not is_read_only(tool):
            # Fail closed: unparseable params or a non-allowlisted tool → no question this turn.
            return InvestigationPlan(max_iters=MAX_DIAGNOSE_ITERS, questions=[])

        params = _coerce_params(tool, params)
        question = DiagnosticQuestion(
            key=f"llm:{tool}:{_params_key(params)}",
            question=str(decision.get("why") or f"call {tool}"),
            call=ToolCallRequest(tool=tool, params=params),
        )
        return InvestigationPlan(max_iters=MAX_DIAGNOSE_ITERS, questions=[question])

    def _ground(self, statement: str, raw_cites: object, produced_refs: set[str]) -> Hypothesis:
        """Build a hypothesis, keeping only citations the tools actually produced. A conclusion with
        no grounded citation is unsupported on purpose — the safety gate then escalates rather than
        shipping an ungrounded root cause."""
        cites = raw_cites if isinstance(raw_cites, list) else []
        grounded = [
            EvidenceCitation(source=ref.split(":", 1)[0], ref=ref, note="cited by the model")
            for ref in cites
            if isinstance(ref, str) and ref in produced_refs
        ]
        if not statement or not grounded:
            return Hypothesis(
                statement=statement or "Root cause undetermined; recommend manual review.",
                confidence=0.3,
                citations=[],
            )
        return Hypothesis(statement=statement, confidence=0.75, citations=grounded)

    def synthesize(
        self,
        ctx: DiagnosisContext,
        observations: list[ToolObservation],
        produced_refs: set[str],
    ) -> Hypothesis:
        """One LLM call that reads the full evidence trail and names the grounded root cause. Run
        when the loop stops (the sufficiency gate ends *gathering*; this ends *reasoning*)."""
        from opspilot.llm.base import ChatMessage

        rendered = self._synth_prompt.text.replace(
            "{incident_context}", _render_context(ctx)
        ).replace("{observations}", _render_observations(observations))
        try:
            decision = extract_json_object(
                self._model.complete([ChatMessage(role="user", content=rendered)]).text
            )
        except ValueError:
            return Hypothesis(
                statement="Root cause undetermined; recommend manual review.",
                confidence=0.2,
                citations=[],
            )
        return self._ground(
            str(decision.get("root_cause") or "").strip(),
            decision.get("citations"),
            produced_refs,
        )

    def revise_hypothesis(
        self,
        base: Hypothesis,
        *,
        ctx: DiagnosisContext | None = None,
        produced_refs: set[str] | None = None,
        observations: list[ToolObservation] | None = None,
        final: bool = False,
    ) -> Hypothesis:
        """While gathering, the provisional (run_cycle) hypothesis stands. On the stopping turn
        (`final`), synthesize the model's grounded conclusion from the full trail."""
        if final and ctx is not None:
            return self.synthesize(ctx, list(observations or ()), set(produced_refs or ()))
        return base

    def wants_to_continue(self, plan: InvestigationPlan, *, answered: set[str]) -> bool:
        """Continue while the model is still proposing a step (a non-empty plan). An empty plan
        means the model said `done` or the step failed closed — stop and let sufficiency + the
        iteration budget decide. Budget bounds any repetition."""
        return bool(plan.questions)
