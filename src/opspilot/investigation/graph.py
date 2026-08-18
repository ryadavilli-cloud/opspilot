"""The investigation graph: six nodes, one continuation loop, one return edge.

```text
  set_objective ──► gather ──► synthesize ──► ground ──► persist ──► deliver
                     ▲  │          │            │
                     │  └─continue─┘            │ one correction, then
                     │                          │ failed execution
                     └───── one return ─────────┘
```

Nodes are ordinary functions. There is no checkpointer, no interrupt, no pause or resume, and no
framework agent abstraction: state lives in memory for one streaming request and is not
recoverable, because an abandoned investigation is meant to leave nothing behind.

Every decision that could let an investigation claim more than it observed is made here, in code,
against computable conditions. The roles propose; this authorizes, counts, admits, grounds, decides
the outcome, and saves. A model cannot widen a bound, mark its own work established, choose its own
outcome, or reach the engineer without passing the gate, because none of those are things it is
ever asked for.

Failure is a first-class path rather than an exception that happens to escape. A failed execution
persists nothing, emits a sanitized category, and is deliberately not an outcome: an investigation
that observed nothing is a different thing from one that observed something and could not settle a
cause, and collapsing them would turn a broken run into a clean bill of health.
"""

# Deliberately no `from __future__ import annotations` in this module. The graph library decides
# whether to hand a node the run configuration by inspecting the `config` annotation, and postponed
# annotations turn it into a string it does not recognize, so it passes None instead and every
# dependency silently goes missing.

from dataclasses import replace
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from opspilot.assessment.brief import outcome_of, render
from opspilot.evidence.admission import admit
from opspilot.grounding.gate import ground as run_gate
from opspilot.investigation.agents import (
    UnusableProposal,
    correct,
    interpret_objective,
    propose_action,
    synthesize,
)
from opspilot.investigation.state import FailureCategory, InvestigationState
from opspilot.record.completed import CompletedInvestigation
from opspilot.record.port import RecordSaveError
from opspilot.stream.projection import emit
from opspilot.tools.service import PROPOSABLE_CAPABILITIES

# What the graph needs from its caller, read off the run configuration rather than closed over, so
# one compiled graph serves every investigation and no request shares another's dependencies.
MODEL = "model"
SERVICE = "service"
RECORD = "record"

# What gathering leaves unspent for the calls that must still happen: one synthesis, and the one
# correction it may need. Without this the cap is not a cap on the run at all, only on gathering,
# and an investigation that spent everything looking would have nothing left to say what it found.
RESERVED_MODEL_CALLS = 2


def _deps(config: RunnableConfig | None) -> dict[str, Any]:
    return dict((config or {}).get("configurable", {}))


def _activity(
    state: InvestigationState,
    name: str,
    *,
    phase: str,
    action: str,
    detail: str,
    status: str = "ok",
    capability: str | None = None,
    outcome: str | None = None,
    references: list[str] | None = None,
) -> list[Any]:
    """One activity entry appended to what the run has already emitted.

    Built at the same call as the telemetry span, from the same stated facts, so the feed and the
    trace cannot drift. Nothing here carries a prompt, a working hypothesis, or provider content.
    """
    event = emit(
        name,
        state.investigation_id,
        state.incident.incident_id,
        sequence=len(state.events) + 1,
        phase=phase,
        action=action,
        status=status,
        detail=detail,
        capability=capability,
        transport="direct" if capability else None,
        outcome=outcome,
        references=references or [],
    )
    return [*state.events, event]


def _record_call(state: InvestigationState, result: Any) -> dict[str, Any]:
    """What one model call adds to the run's account of itself."""
    versions = state.prompt_versions
    if result.prompt_version and result.prompt_version not in versions:
        versions = [*versions, result.prompt_version]
    return {
        "model_calls_made": state.model_calls_made + 1,
        "model_deployment": result.deployment or state.model_deployment,
        "prompt_versions": versions,
    }


def _failed(state: InvestigationState, category: FailureCategory, detail: str) -> dict[str, Any]:
    return {
        "failure": category,
        "events": _activity(
            state,
            "investigation.failed",
            phase="failed",
            action="execution failed",
            status="error",
            detail=detail,
            outcome=category.value,
        ),
    }


# --- nodes ----------------------------------------------------------------------------------
def set_objective(
    state: InvestigationState, config: RunnableConfig | None = None
) -> dict[str, Any]:
    """The Supervisor states what the investigation must establish. Bounds are already set."""
    if state.bounds.expired:
        return _failed(state, FailureCategory.DEADLINE_EXPIRED, "the deadline expired before work")

    objective, result = interpret_objective(_deps(config)[MODEL], state.incident)
    update = _record_call(state, result)
    return {
        **update,
        "objective": objective,
        "events": _activity(
            state,
            "investigation.objective",
            phase="objective",
            action="objective set",
            detail=objective,
        ),
    }


def gather(state: InvestigationState, config: RunnableConfig | None = None) -> dict[str, Any]:
    """One proposal, authorized deterministically, then executed and admitted.

    Gathering ends the moment a condition fails rather than skipping the proposal and asking again:
    the investigator is choosing under bounds it can see, so a refusal is information about the run
    and is recorded as the reason it stopped.
    """
    deps = _deps(config)
    if state.bounds.expired:
        return {"stopped_because": "the deadline expired while gathering"}
    if state.model_calls_made + RESERVED_MODEL_CALLS >= state.bounds.model_calls:
        return {"stopped_because": "the model-call cap is spent"}

    action, result = propose_action(
        deps[MODEL],
        state.incident,
        state.objective,
        state.evidence,
        PROPOSABLE_CAPABILITIES,
    )
    update = _record_call(state, result)

    if action.is_finished:
        return {**update, "stopped_because": action.finished_because}

    refusal = _refuse(state, action, PROPOSABLE_CAPABILITIES)
    if refusal:
        return {
            **update,
            "stopped_because": refusal,
            "events": _activity(
                state,
                "investigation.refused",
                phase="gathering",
                action="proposal refused",
                status="error",
                detail=refusal,
            ),
        }

    tool_result = deps[SERVICE].call(action.capability, **action.arguments)
    admitted = admit(
        tool_result,
        evidence=state.evidence,
        question=action.question,
        request_scope=action.arguments,
    )
    return {
        **update,
        "evidence": state.evidence,
        "capability_calls_made": state.capability_calls_made + 1,
        "answered_questions": state.answered_questions | {action.question},
        "executed_calls": state.executed_calls | {_call_signature(action)},
        "events": _activity(
            state,
            "investigation.capability",
            phase="gathering",
            action=action.capability,
            detail=(
                f"{action.capability}: {tool_result.outcome.value}, "
                f"{tool_result.completeness.value} ({len(admitted)} admitted)"
            ),
            capability=action.capability,
            outcome=tool_result.outcome.value,
            references=[obs.evidence_ref for obs in admitted],
        ),
    }


def _call_signature(action: Any) -> str:
    """One call, as the thing that decides whether it has already been made.

    The capability and its arguments, not the sentence wrapped around them: the same query asked
    in different words is the same query, and its answer is already held.
    """
    arguments = ", ".join(f"{key}={value!r}" for key, value in sorted(action.arguments.items()))
    return f"{action.capability}({arguments})"


def _refuse(state: InvestigationState, action: Any, registered: tuple[str, ...]) -> str:
    """The deterministic authorization conditions, in the order they are cheapest to check."""
    if action.capability not in registered:
        return f"{action.capability} is not a registered capability"
    if action.question in state.answered_questions:
        return f"the question {action.question!r} was already answered"
    if _call_signature(action) in state.executed_calls:
        return f"{_call_signature(action)} was already called and answered"
    if not state.capability_budget_left:
        return "the capability-call cap is spent"
    return ""


def synthesize_node(
    state: InvestigationState, config: RunnableConfig | None = None
) -> dict[str, Any]:
    """The RCA Analyst proposes; structural admission decides only whether it is usable at all."""
    if not state.evidence.observations:
        return _failed(
            state,
            FailureCategory.NO_EVIDENCE,
            "no operational evidence was admitted, so nothing could rest on anything observed",
        )
    if state.bounds.expired:
        return _failed(
            state, FailureCategory.DEADLINE_EXPIRED, "the deadline expired before synthesis"
        )
    if not state.model_budget_left:
        return _failed(
            state,
            FailureCategory.UNUSABLE_ASSESSMENT,
            "the model-call cap was spent before an assessment could be proposed",
        )

    deps = _deps(config)
    try:
        assessment, result = synthesize(
            deps[MODEL], state.incident, state.objective, state.evidence, state.stopped_because
        )
    except UnusableProposal as exc:
        return _spend_correction(state, deps[MODEL], str(exc), FailureCategory.UNUSABLE_ASSESSMENT)

    return {
        **_record_call(state, result),
        "assessment": assessment,
        "events": _activity(
            state,
            "investigation.synthesis",
            phase="synthesizing",
            action="assessment proposed",
            detail=(
                f"{len(assessment.candidates)} candidate(s), "
                f"{len(assessment.established)} established, "
                f"{len(assessment.limitations)} limitation(s)"
            ),
        ),
    }


def _spend_correction(
    state: InvestigationState, model: Any, problem: str, category: FailureCategory
) -> dict[str, Any]:
    """The one corrective call, or the failure that follows when it is unavailable or spent."""
    if state.bounds.correction_used or not state.model_budget_left:
        return _failed(state, category, f"unrecoverable after the one correction: {problem}")

    state.bounds.correction_used = True
    try:
        assessment, result = correct(
            model,
            state.incident,
            state.objective,
            state.evidence,
            state.stopped_because,
            problem,
        )
    except UnusableProposal as exc:
        return _failed(state, category, f"the correction was also unusable: {exc}")

    return {
        **_record_call(state, result),
        "assessment": assessment,
        "issues": [],
        "events": _activity(
            state,
            "investigation.correction",
            phase="grounding",
            action="assessment corrected",
            detail=f"one corrective call was spent: {problem}",
        ),
    }


def ground(state: InvestigationState, config: RunnableConfig | None = None) -> dict[str, Any]:
    """The gate runs, reports, and edits nothing. Issues route to the one correction, then fail."""
    if state.failure or state.assessment is None:
        return {}

    issues = run_gate(
        state.assessment,
        admitted_refs=set(state.evidence.admitted_refs),
        knowledge_refs=set(),
        limitations=state.evidence.limitations,
    )
    if not issues:
        return {
            "issues": [],
            "events": _activity(
                state,
                "investigation.grounded",
                phase="grounding",
                action="grounding passed",
                detail="every claim rests on evidence this investigation admitted",
            ),
        }

    problem = "; ".join(str(issue) for issue in issues)
    corrected = _spend_correction(
        state, _deps(config)[MODEL], problem, FailureCategory.UNGROUNDED_ASSESSMENT
    )
    if corrected.get("failure") or corrected.get("assessment") is None:
        return corrected

    # Re-checked rather than trusted: a correction is another proposal, not a repair.
    remaining = run_gate(
        corrected["assessment"],
        admitted_refs=set(state.evidence.admitted_refs),
        knowledge_refs=set(),
        limitations=state.evidence.limitations,
    )
    if remaining:
        detail = "; ".join(str(issue) for issue in remaining)
        # The failure entry is appended to what the correction already emitted, not to what the
        # state held before it. Rebuilding from the older list would drop the correction's own
        # entry, and a feed that never showed the attempt would make the run look as though it
        # failed without one.
        spent = replace(state, events=corrected["events"])
        return {**corrected, **_failed(spent, FailureCategory.UNGROUNDED_ASSESSMENT, detail)}
    return corrected


def persist(state: InvestigationState, config: RunnableConfig | None = None) -> dict[str, Any]:
    """Outcome, then save. Nothing is delivered before this succeeds."""
    if state.failure or state.assessment is None:
        return {}

    outcome = outcome_of(state.assessment)
    brief = render(state.assessment)
    record = CompletedInvestigation(
        investigation_id=state.investigation_id,
        incident_id=state.incident.incident_id,
        objective=state.objective,
        outcome=outcome,
        stopped_because=state.stopped_because,
        assessment=state.assessment,
        brief=brief,
        model_deployment=state.model_deployment,
        observations=tuple(state.evidence.observations),
        limitations=tuple(state.evidence.limitations),
        operations=tuple(state.evidence.operations),
        prompt_versions=tuple(state.prompt_versions),
    )
    try:
        _deps(config)[RECORD].save(record)
    except RecordSaveError as exc:
        return _failed(state, FailureCategory.SAVE_FAILED, f"the record could not be saved: {exc}")

    return {
        "outcome": outcome,
        "events": _activity(
            state,
            "investigation.persisted",
            phase="persisting",
            action="record saved",
            detail=f"the completed investigation was saved as {outcome.value}",
            outcome=outcome.value,
        ),
    }


def deliver(state: InvestigationState, config: RunnableConfig | None = None) -> dict[str, Any]:
    """The last activity entry. The terminal event itself is the streaming request's to emit, once
    this has returned and the record is already written."""
    if state.failure:
        return {}
    return {
        "events": _activity(
            state,
            "investigation.delivered",
            phase="delivering",
            action="brief ready",
            detail="the brief is ready to deliver",
        )
    }


# --- edges ----------------------------------------------------------------------------------
def _after_objective(state: InvestigationState) -> str:
    return END if state.failure else "gather"


def _after_gather(state: InvestigationState) -> str:
    """Continue while the investigator has something useful and permitted left to ask."""
    if state.failure:
        return END
    return "synthesize" if state.stopped_because else "gather"


def _after_synthesis(state: InvestigationState) -> str:
    """The return edge is declared here and is not followed yet: authorizing one costs a bound and
    a question, and nothing proposes one until the slice that exercises it."""
    if state.failure:
        return END
    return "ground"


def _after_ground(state: InvestigationState) -> str:
    return END if state.failure else "persist"


def _after_persist(state: InvestigationState) -> str:
    return END if state.failure else "deliver"


def build_graph() -> Any:
    """One compiled graph, no checkpointer. Dependencies arrive per run on the configuration."""
    graph = StateGraph(InvestigationState)
    graph.add_node("set_objective", set_objective)
    graph.add_node("gather", gather)
    graph.add_node("synthesize", synthesize_node)
    graph.add_node("ground", ground)
    graph.add_node("persist", persist)
    graph.add_node("deliver", deliver)

    graph.set_entry_point("set_objective")
    graph.add_conditional_edges("set_objective", _after_objective, {"gather": "gather", END: END})
    graph.add_conditional_edges(
        "gather", _after_gather, {"gather": "gather", "synthesize": "synthesize", END: END}
    )
    graph.add_conditional_edges(
        "synthesize", _after_synthesis, {"ground": "ground", "gather": "gather", END: END}
    )
    graph.add_conditional_edges("ground", _after_ground, {"persist": "persist", END: END})
    graph.add_conditional_edges("persist", _after_persist, {"deliver": "deliver", END: END})
    graph.add_edge("deliver", END)
    return graph.compile()
