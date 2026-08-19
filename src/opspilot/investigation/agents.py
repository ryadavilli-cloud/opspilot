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
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from opspilot.assessment.contracts import Assessment
from opspilot.assessment.synthesis import (
    SYNTHESIS_TASK,
    UnresolvedQuestion,
    UnusableProposal,
    admit_assessment,
    parse_proposal,
)
from opspilot.evidence.admission import CAPABILITY_EVIDENCE_TYPES, AdmittedObservation
from opspilot.evidence.operations import EvidenceSet
from opspilot.llm.base import ChatMessage, ChatResult
from opspilot.llm.prompts import Prompt, get_prompt
from opspilot.retrieval.retriever import Passage
from opspilot.tools import CAPABILITY_NAMES
from opspilot.tools.contracts import Completeness
from opspilot.tools.service import (
    capability_arguments,
    capability_purpose,
    structured_query_surface,
)

OBJECTIVE_TASK = "investigation_objective"
SELECTION_TASK = "evidence_selection"
CORRECTION_TASK = "assessment_correction"

# What a further pass could actually obtain: the evidence kinds supplied by the capabilities the
# investigator may propose. Derived from the two facts that already decide it, so a capability
# that becomes proposable brings its kind with it and no second list can fall behind. The
# analyst is shown these and the Supervisor authorizes against them, so both sides of the return
# read the same vocabulary and the decision stays a membership test.
RETURNABLE_EVIDENCE_KINDS: tuple[str, ...] = tuple(
    sorted(
        {
            kind.value
            for name in CAPABILITY_NAMES
            if (kind := CAPABILITY_EVIDENCE_TYPES.get(name)) is not None
        }
    )
)


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


def _ask(model: Any, task: str, prompt: Prompt, user: str) -> ChatResult:
    """One model call, with the prompt version it was made under stamped onto the result.

    The seam returns which deployment answered and what the call cost; which prompt asked is the
    caller's to know, because only the caller resolved it from the registry. Stamping it here is
    what lets the completed record say what produced it, and a record that cannot name its prompt
    version cannot be compared against a later run that changed it.
    """
    result: ChatResult = model.complete(
        task,
        [
            ChatMessage(role="system", content=prompt.text),
            ChatMessage(role="user", content=user),
        ],
    )
    return replace(result, prompt_version=prompt.version)


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


def knowledge_digest(knowledge: Sequence[Passage]) -> str:
    """What the run retrieved, rendered so it can never be mistaken for what it observed.

    Every line is labelled as knowledge, and the heading says what knowledge is for. A passage is
    what someone wrote down before this incident happened, so it can explain a mechanism or point
    at a precedent, and it cannot show that anything is true of the system right now. The grounding
    gate refuses a knowledge reference offered as current operational support; saying so here gives
    a role the chance to get that right rather than be corrected for it.
    """
    lines = ["Retrieved knowledge (background and precedent, not evidence about this incident):"]
    if knowledge:
        lines.extend(
            f"- {passage.reference} [{passage.category}] {passage.title}: {passage.text}"
            for passage in knowledge
        )
    else:
        lines.append("- (nothing retrieved)")
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


def _attempts(evidence: EvidenceSet) -> str:
    """What has already been tried, and how each attempt ended.

    Without this the investigator is blind to its own history whenever a call adds nothing: a
    query whose every row was already admitted leaves the evidence digest unchanged, so the next
    prompt is byte-identical to the last and the same choice looks equally good a second time. The
    operations list is part of the evidence set for exactly this reason, and showing it is what
    lets an agent move on rather than circle.
    """
    if not evidence.operations:
        return "Calls already made: (none)"
    lines = ["Calls already made (do not repeat any of these):"]
    lines.extend(f"- {op.capability}: {op.outcome.value}" for op in evidence.operations)
    return "\n".join(lines)


def interpret_objective(model: Any, incident: Any) -> tuple[str, ChatResult]:
    """The Supervisor's one model call: what is this investigation trying to establish?

    An unreadable answer falls back to the incident's own words rather than failing the run. The
    objective frames the work; it is not a finding, and nothing downstream rests on its wording.
    """
    prompt = get_prompt("investigation_objective")
    result = _ask(model, OBJECTIVE_TASK, prompt, "\n".join(_incident_lines(incident)))
    stated = str(_json_object(result.text).get("objective", "")).strip()
    return stated or f"Establish what caused: {incident.symptom}", result


# The one capability whose request is a structure rather than flat arguments, so the one that needs
# more than its signature stated. Named here so that withdrawing it from what is offered also
# withdraws its description, rather than leaving a block explaining something no caller may propose.
STRUCTURED_QUERY = "structured_query"


def propose_action(
    model: Any,
    incident: Any,
    objective: str,
    evidence: EvidenceSet,
    knowledge: Sequence[Passage],
    capabilities: tuple[str, ...],
    calls_left: int,
    open_question: str = "",
) -> tuple[ProposedAction, ChatResult]:
    """The Evidence Investigator's one call per step: which capability, with what, to answer what.

    What it may choose from is stated rather than assumed: the registered capabilities, the
    incident, the objective, and what has been admitted so far. A proposal naming something else is
    refused by the Supervisor, not filtered here, so the refusal is visible in the feed.

    `open_question` is set on the one step that resumes gathering after analysis returned. It is
    what the analyst could not answer, handed back as the thing to go and answer. It is stated
    rather than imposed: the investigator still proposes, and the Supervisor still authorizes under
    the same rules, so a question that turns out to need something already asked is refused like any
    other repeat rather than granted because analysis wanted it.

    `calls_left` is the budget, stated. A role that cannot see what it has left cannot spend it
    well: it behaves as though calls were free, works down whatever it was offered, and reaches the
    end having asked everything once. Showing it widens nothing, because the count is code's and
    authorization stays code's; it only lets the choice be made by someone who knows the cost.
    """
    prompt = get_prompt("evidence_selection")
    user = "\n".join(
        [
            *_incident_lines(incident),
            f"Objective: {objective}",
            "",
            *(
                [
                    "Analysis could not settle this and sent the investigation back for it. "
                    "Answer it if a capability below can:",
                    f"- {open_question}",
                    "",
                ]
                if open_question
                else []
            ),
            "Capabilities you may choose from, what each answers, and the arguments each takes",
            "(bracketed arguments are optional):",
            *(
                f"- {name}({capability_arguments(name)}): {capability_purpose(name)}"
                for name in capabilities
            ),
            *(["", structured_query_surface()] if STRUCTURED_QUERY in capabilities else []),
            "",
            f"Calls you have left: {calls_left}. There are {len(capabilities)} capabilities, "
            "so you cannot use them all. Spend what is left on what would change the conclusion.",
            "",
            _attempts(evidence),
            "",
            evidence_digest(evidence),
            "",
            knowledge_digest(knowledge),
        ]
    )
    result = _ask(model, SELECTION_TASK, prompt, user)
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


def _synthesis_user_message(
    incident: Any,
    objective: str,
    evidence: EvidenceSet,
    knowledge: Sequence[Passage],
    why: str,
    *,
    returned: bool = False,
) -> str:
    return "\n".join(
        [
            f"Objective: {objective}",
            *_incident_lines(incident),
            f"Gathering ended because: {why}",
            "",
            *(
                [
                    "This investigation has already been sent back to gather once, which is all it "
                    "may do. Whatever remains unanswered now stands as an unknown.",
                    "",
                ]
                if returned
                else [
                    "If something material remains unanswered and one of these kinds of evidence "
                    "could answer it, say so in `unresolved_question` using the kind's own name:",
                    *(f"- {kind}" for kind in RETURNABLE_EVIDENCE_KINDS),
                    "",
                ]
            ),
            evidence_digest(evidence),
            "",
            knowledge_digest(knowledge),
        ]
    )


def synthesize(
    model: Any,
    incident: Any,
    objective: str,
    evidence: EvidenceSet,
    knowledge: Sequence[Passage],
    stopped_because: str,
    *,
    returned: bool = False,
) -> tuple[Assessment, UnresolvedQuestion | None, ChatResult]:
    """The RCA Analyst's one call. Raises `UnusableProposal` when nothing can be made of it.

    The routing field travels beside the assessment rather than inside it. It is what the analyst
    could not settle, which is a fact about this run rather than a finding about the incident: the
    assessment states the same matter in `unknowns` and stands whether or not anything acts on it.

    `returned` says a return has already been spent, which the analyst is told because it changes
    what an honest answer looks like: with no further pass available, an open question is an unknown
    to report rather than work to request.
    """
    prompt = get_prompt("rca_synthesis")
    user = _synthesis_user_message(
        incident, objective, evidence, knowledge, stopped_because, returned=returned
    )
    result = _ask(model, SYNTHESIS_TASK, prompt, user)
    proposal = parse_proposal(result.text)
    return admit_assessment(proposal), proposal.unresolved_question, result


def correct(
    model: Any,
    incident: Any,
    objective: str,
    evidence: EvidenceSet,
    knowledge: Sequence[Passage],
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
            _synthesis_user_message(incident, objective, evidence, knowledge, stopped_because),
            "",
            "Your previous assessment could not be delivered:",
            problem,
        ]
    )
    result = _ask(model, CORRECTION_TASK, prompt, user)
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
    "knowledge_digest",
    "propose_action",
    "synthesize",
]
