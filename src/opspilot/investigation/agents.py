"""The three model-directed roles, and only the parts of them a model actually decides.

Each function here is one bounded model call and the parsing of what came back. Nothing here
authorizes, counts, bounds, admits, or concludes: a role proposes, and the graph decides. That
split is the whole point of the arrangement, so it is worth being blunt about where the line falls.

- The **Supervisor** interprets the incident into an objective. Everything else it does is code.
- The **Evidence Investigator** proposes one capability call at a time and says when it has what it
  needs. It never reaches a tool itself and its working hypothesis stays here, never reaching the
  engineer.
- The **RCA Analyst** proposes one assessment, and once more if the first was unusable. It reaches
  no tool at all.

A response that cannot be read degrades to the honest reading rather than raising: an objective
falls back to the incident's own words, and a proposal that names nothing becomes the investigator
saying it has nothing further to ask. Neither invents work, and neither lets a malformed response
end the run on a technicality.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from opspilot.assessment.contracts import Assessment
from opspilot.assessment.synthesis import (
    SYNTHESIS_TASK,
    UnusableProposal,
    admit_assessment,
    parse_proposal,
)
from opspilot.evidence.admission import AdmittedObservation
from opspilot.evidence.operations import EvidenceSet
from opspilot.llm.base import ChatMessage, ChatResult
from opspilot.llm.prompts import get_prompt
from opspilot.tools.contracts import Completeness

OBJECTIVE_TASK = "investigation_objective"
SELECTION_TASK = "evidence_selection"
CORRECTION_TASK = "assessment_correction"


@dataclass(frozen=True)
class ProposedAction:
    """What the investigator wants next, or its statement that nothing further is useful.

    One shape rather than two, because "propose a call" and "report you are done" are the same
    decision made once. An empty capability is the finished form, and the reason travels with it so
    the activity feed can say why gathering stopped in the investigator's own terms.
    """

    capability: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    question: str = ""
    finished_because: str = ""

    @property
    def is_finished(self) -> bool:
        return not self.capability


def _json_object(text: str) -> dict[str, Any]:
    """The first JSON object in a response, or an empty one. Models wrap JSON in fences."""
    cleaned = (text or "").strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        parsed = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def evidence_digest(evidence: EvidenceSet) -> str:
    """What a role reasons over: admitted observations by reference, and what went unanswered.

    A partial observation says so on its own line. The source answered over part of the requested
    scope, and a reader taking it as the whole picture would claim more than was observed.
    """
    lines = ["Admitted evidence:"]
    if evidence.observations:
        lines.extend(_observation_line(obs) for obs in evidence.observations)
    else:
        lines.append("- (none)")
    if evidence.limitations:
        lines.append("Could not be established:")
        lines.extend(f"- {limitation}" for limitation in evidence.limitations)
    return "\n".join(lines)


def _observation_line(obs: AdmittedObservation) -> str:
    partial = " [partial]" if obs.completeness is Completeness.PARTIAL else ""
    return f"- {obs.evidence_ref} [{obs.evidence_type.value}]{partial} {obs.observation}"


def _incident_lines(incident: Any) -> list[str]:
    lines = [f"Incident: {incident.incident_id}", f"Reported symptom: {incident.symptom}"]
    if incident.scope:
        lines.append(f"Scope: {incident.scope}")
    lines.append(f"Time anchor: {incident.time_anchor.isoformat()}")
    return lines


def interpret_objective(model: Any, incident: Any) -> tuple[str, ChatResult]:
    """The Supervisor's one model call: what is this investigation trying to establish?

    An unreadable answer falls back to the incident's own words rather than failing the run. The
    objective frames the work; it is not a finding, and nothing downstream rests on its wording.
    """
    prompt = get_prompt("investigation_objective")
    result = model.complete(
        OBJECTIVE_TASK,
        [
            ChatMessage(role="system", content=prompt.text),
            ChatMessage(role="user", content="\n".join(_incident_lines(incident))),
        ],
    )
    stated = str(_json_object(result.text).get("objective", "")).strip()
    return stated or f"Establish what caused: {incident.symptom}", result


def propose_action(
    model: Any, incident: Any, objective: str, evidence: EvidenceSet, capabilities: tuple[str, ...]
) -> tuple[ProposedAction, ChatResult]:
    """The Evidence Investigator's one call per step: which capability, with what, to answer what.

    What it may choose from is stated rather than assumed: the registered capabilities, the
    incident, the objective, and what has been admitted so far. A proposal naming something else is
    refused by the Supervisor, not filtered here, so the refusal is visible in the feed.
    """
    prompt = get_prompt("evidence_selection")
    user = "\n".join(
        [
            *_incident_lines(incident),
            f"Objective: {objective}",
            f"Registered capabilities: {', '.join(capabilities)}",
            "",
            evidence_digest(evidence),
        ]
    )
    result = model.complete(
        SELECTION_TASK,
        [
            ChatMessage(role="system", content=prompt.text),
            ChatMessage(role="user", content=user),
        ],
    )
    payload = _json_object(result.text)

    capability = str(payload.get("capability", "")).strip()
    if not capability:
        finished = str(payload.get("finished_because", "")).strip()
        return ProposedAction(
            finished_because=finished or "the investigator proposed no further action"
        ), result

    arguments = payload.get("arguments")
    return ProposedAction(
        capability=capability,
        arguments=arguments if isinstance(arguments, dict) else {},
        question=str(payload.get("question", "")).strip(),
    ), result


def _synthesis_user_message(incident: Any, objective: str, evidence: EvidenceSet, why: str) -> str:
    return "\n".join(
        [
            f"Objective: {objective}",
            *_incident_lines(incident),
            f"Gathering ended because: {why}",
            "",
            evidence_digest(evidence),
        ]
    )


def synthesize(
    model: Any, incident: Any, objective: str, evidence: EvidenceSet, stopped_because: str
) -> tuple[Assessment, ChatResult]:
    """The RCA Analyst's one call. Raises `UnusableProposal` when nothing can be made of it."""
    prompt = get_prompt("rca_synthesis")
    result = model.complete(
        SYNTHESIS_TASK,
        [
            ChatMessage(role="system", content=prompt.text),
            ChatMessage(
                role="user",
                content=_synthesis_user_message(incident, objective, evidence, stopped_because),
            ),
        ],
    )
    return admit_assessment(parse_proposal(result.text)), result


def correct(
    model: Any,
    incident: Any,
    objective: str,
    evidence: EvidenceSet,
    stopped_because: str,
    problem: str,
) -> tuple[Assessment, ChatResult]:
    """The one corrective call, carrying what was wrong with the first attempt.

    It re-proposes rather than edits: the analyst is told the problem and asked again, so what the
    gate sees the second time is still a whole proposal the analyst stands behind, not a patched
    one nothing produced.
    """
    prompt = get_prompt("assessment_correction")
    user = "\n".join(
        [
            _synthesis_user_message(incident, objective, evidence, stopped_because),
            "",
            "Your previous assessment could not be delivered:",
            problem,
        ]
    )
    result = model.complete(
        CORRECTION_TASK,
        [
            ChatMessage(role="system", content=prompt.text),
            ChatMessage(role="user", content=user),
        ],
    )
    return admit_assessment(parse_proposal(result.text)), result


__all__ = [
    "CORRECTION_TASK",
    "OBJECTIVE_TASK",
    "SELECTION_TASK",
    "ProposedAction",
    "UnusableProposal",
    "correct",
    "evidence_digest",
    "interpret_objective",
    "propose_action",
    "synthesize",
]
