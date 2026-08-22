"""The HTTP surface: health, version, the screen, and one streaming investigation.

Health is split three ways so an orchestrator can tell the states apart:
  - `/health/live`   the process is running, touching nothing else
  - `/health/ready`  the revision can serve an investigation: the operational-records container
                     answers a seeded lookup and retrieval came up as the configured backend.
                     503 when not
  - `/version`       build and runtime metadata

`POST /investigations` is the only investigative route. One live streaming request owns one
investigation: identity first, then activity as it happens, then exactly one terminal event
carrying the brief or a sanitized failure category. There is no job, no polling, and no resumption.
If the request disconnects the run is abandoned, which is safe precisely because the record is
written before the terminal event or not at all.

Beside it, one read-only page lists every completed investigation and every kept evaluation run
and shows one of either in full. The routes behind it only read: nothing here creates, triggers,
edits, or deletes a record or a run, and the application holds no write on the run container.

Errors never expose a stack trace, a path, or a secret.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, StringConstraints

from opspilot import __version__, config
from opspilot.assessment.brief import render
from opspilot.config import ENVIRONMENT, RETRIEVAL_BACKEND
from opspilot.data.operational_records import (
    OperationalRecords,
    default_operational_records,
)
from opspilot.evaluation.record import EvaluationRun, EvaluationRunSummary
from opspilot.evaluation.store import EvaluationRunRepository
from opspilot.evidence.operations import EvidenceSet
from opspilot.intake.contracts import from_predefined_incident
from opspilot.investigation.agents import answer_question
from opspilot.investigation.graph import MODEL, RECORD, SERVICE, build_graph
from opspilot.investigation.state import Bounds, FailureCategory, InvestigationState
from opspilot.obs import tracing
from opspilot.record.completed import CompletedInvestigation, InvestigationSummary
from opspilot.record.port import CompletedInvestigationRepository
from opspilot.startup import configuration_problems, startup_record
from opspilot.stream.contracts import IdentityEvent, TerminalEvent
from opspilot.tools.contracts import Completeness, IncidentRecord

_log = logging.getLogger("opspilot.api")


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Check the configuration once, then say what this revision is.

    A misconfigured deployment refuses to start rather than accepting a request it cannot serve.
    The alternative is failing inside an investigation, where the same missing setting reads as an
    unavailable source and sends whoever is looking to the wrong place entirely.

    Local runs are exempt from the required-setting half by `configuration_problems` itself, so the
    tests and a developer running against the corpus fake start as they always did. A setting whose
    value names nothing that exists is refused everywhere, because that is a mistake in any
    environment.
    """
    problems = configuration_problems()
    if problems:
        for problem in problems:
            _log.error("configuration: %s", problem)
        raise RuntimeError(f"refusing to start: {len(problems)} configuration problem(s); see log")

    # Apply the exporter the configuration names. Without this the module keeps the one it was born
    # with, which discards every span, and a revision configured for telemetry emits none while
    # looking configured. The setting is validated above; this is what makes it mean anything.
    tracing.configure_exporter()

    _log.info("startup: %s", startup_record())
    yield


app = FastAPI(title="OpsPilot", version=__version__, lifespan=_lifespan)

# The one-screen client: a self-contained, same-origin page with no build step, read once at import
# because it is a packaged asset rather than runtime-configurable data.
_INVESTIGATION_HTML = (Path(__file__).parent / "static" / "investigation.html").read_text(
    encoding="utf-8"
)
# The read-only page over completed investigations and kept evaluation runs, same shape and same
# reasons.
_AGENTOPS_HTML = (Path(__file__).parent / "static" / "agentops.html").read_text(encoding="utf-8")

# Every lazy singleton below is built under this lock. `if x is None: x = build()` is a
# check-then-act race: two concurrent first requests both observe None and both construct, which
# for the graph would mean two compiled graphs and for the record two separate stores.
_singleton_lock = threading.Lock()

_graph: Any = None
_tool_service: Any = None
_model: Any = None
_record: CompletedInvestigationRepository | None = None
_evaluation_runs: EvaluationRunRepository | None = None
_operational_records: OperationalRecords | None = None


def get_graph() -> Any:
    """One compiled graph per process. Dependencies arrive per run on the configuration, so the
    graph holds nothing belonging to any one investigation."""
    global _graph
    if _graph is None:
        with _singleton_lock:
            if _graph is None:
                _graph = build_graph()
    return _graph


def get_service() -> Any:
    """One capability registry per process, injected so a test can supply its own backing."""
    global _tool_service
    if _tool_service is None:
        with _singleton_lock:
            if _tool_service is None:
                from opspilot.tools.service import ToolService

                _tool_service = ToolService()
    return _tool_service


def get_model() -> Any:
    """The chat model every task runs on. Built lazily so importing this module opens nothing."""
    global _model
    if _model is None:
        with _singleton_lock:
            if _model is None:
                from opspilot.llm.client import build_chat_model

                _model = build_chat_model()
    return _model


def get_record() -> CompletedInvestigationRepository:
    """Where a completed investigation is written, and read back from afterwards.

    The deployed container, built once per process and lazily, so importing this module needs no
    credential. It has to be the durable one: a question about a completed investigation is a
    second request, and under more than one replica it can land on an instance that never ran the
    investigation. A process-local store would not make that flaky, it would make it wrong, and a
    hosted proof that passed would have passed by luck.

    Substitution is the seam's purpose and stays where it already is: a test overrides this
    dependency and never reaches the factory below. There is deliberately no setting choosing
    between the two, because a second way to be wrong about which store is live is worse than none,
    and readiness already reports which one answered.
    """
    global _record
    if _record is None:
        with _singleton_lock:
            if _record is None:
                from opspilot.record.cosmos import default_completed_investigations

                _record = default_completed_investigations()
    return _record


def get_evaluation_runs() -> EvaluationRunRepository:
    """Where kept evaluation runs are read from.

    Read and never written from here: the evaluation runner writes this container under its own
    principal, and the application's identity holds read on it and nothing more, so the line is
    held by the role assignment rather than by this module declining to call `save`. Built once
    per process and lazily, like the record, and substituted by tests the same way.
    """
    global _evaluation_runs
    if _evaluation_runs is None:
        with _singleton_lock:
            if _evaluation_runs is None:
                from opspilot.evaluation.store import default_evaluation_runs

                _evaluation_runs = default_evaluation_runs()
    return _evaluation_runs


def get_operational_records() -> OperationalRecords:
    """The read-only reader intake resolves an incident against.

    Separate from the capability registry on purpose: selecting the incident is not evidence
    gathering, and the interface must not reach an operational capability.
    """
    global _operational_records
    if _operational_records is None:
        with _singleton_lock:
            if _operational_records is None:
                _operational_records = default_operational_records()
    return _operational_records


# --------------------------------------------------------------------------------------
# Contracts
# --------------------------------------------------------------------------------------
class StartInvestigationRequest(BaseModel):
    """Intake: select one authored incident to investigate."""

    incident_id: str


class LivenessResponse(BaseModel):
    status: Literal["alive"] = "alive"
    version: str


class ReadinessError(BaseModel):
    component: str
    code: str


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, str]
    retrieval_backend: str
    version: str
    errors: list[ReadinessError] | None = None


class VersionResponse(BaseModel):
    application: str = "opspilot"
    version: str
    environment: str
    retrieval_backend: str


# --------------------------------------------------------------------------------------
# Screen
# --------------------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """The way in, for a person who was given the address and nothing else.

    Where the deployment is behind built-in authentication, this is the one path left open, and it
    exists to hand a visitor to the sign-in the platform serves rather than to the screen, which
    would answer them with a bare 401. Signing in returns them here and they arrive at the screen.
    Someone already signed in passes straight through.

    Locally there is no platform in front of this and nothing serves that path, so the screen is
    where a visitor should go directly.
    """
    # Read from the module rather than a name bound at import, so what a process reports and what
    # it does here cannot disagree.
    if config.ENVIRONMENT == "local":
        return RedirectResponse("/investigation")
    return RedirectResponse("/.auth/login/aad?post_login_redirect_uri=%2Finvestigation")


@app.get("/investigation", response_class=HTMLResponse, include_in_schema=False)
def investigation() -> str:
    """Intake, a compact live activity feed, the brief as the dominant element once it arrives,
    and one expandable details area."""
    return _INVESTIGATION_HTML


@app.get("/agentops", response_class=HTMLResponse, include_in_schema=False)
def agentops() -> str:
    """Every completed investigation and every kept evaluation run, listed and readable.

    Read-only by construction: the page fetches from the listing and reading routes below and
    nothing else, and no route it could reach starts, triggers, edits, or deletes anything.
    """
    return _AGENTOPS_HTML


# --------------------------------------------------------------------------------------
# Health and version
# --------------------------------------------------------------------------------------
@app.get("/health/live")
def live() -> LivenessResponse:
    """Liveness: the process is up. Touches no corpus, retrieval, capability, or external system."""
    return LivenessResponse(version=__version__)


@app.get("/health")
def health() -> LivenessResponse:
    """Deprecated alias for /health/live, kept so existing probes do not break."""
    return live()


@app.get("/version")
def version() -> VersionResponse:
    return VersionResponse(
        version=__version__,
        environment=ENVIRONMENT,
        retrieval_backend=RETRIEVAL_BACKEND,
    )


def _check(fn: Any) -> bool:
    """Run a readiness probe, treating any failure as a failed rather than a raising check."""
    try:
        return bool(fn())
    except Exception:  # noqa: BLE001 - readiness converts every failure into a failed check
        return False


def _safe_backend(svc: Any) -> str:
    try:
        return str(svc.retrieval_backend)
    except Exception:  # noqa: BLE001
        return "unavailable"


@app.get("/health/ready")
def ready(response: Response, svc: Any = Depends(get_service)) -> ReadinessResponse:
    """Whether this revision can serve an investigation, in two cheap questions.

    A readiness probe runs for the life of the revision, on a period far shorter than the work it
    guards, so what it costs is paid continuously and what it holds open is held open the whole
    time. It therefore asks the least that still distinguishes a revision that cannot work from one
    that can: the operational source answers and is seeded, and retrieval came up as the backend
    this build was configured for.

    It deliberately does not embed a query, search the index, or count the corpus. Those exercise
    the investigative path, which is what the deployment smoke run does once, against the revision,
    with a whole investigation. Doing it here would repeat a model-serving call every few seconds
    for as long as the revision lives, and would make a rate-limited embedding endpoint read as an
    application that is not ready.
    """
    checks: dict[str, str] = {}
    errors: list[ReadinessError] = []
    backend = _safe_backend(svc)

    def record(name: str, ok: bool, code: str) -> None:
        checks[name] = "ok" if ok else "failed"
        if not ok:
            errors.append(ReadinessError(component=name, code=code))

    def records_ok() -> bool:
        # One point read. Completeness is read too, because a reachable but unseeded container
        # answers succeeded with empty, which is a true answer and still not a ready deployment.
        result = svc.get_incident(incident_id="inc-004")
        return bool(result.answered and result.completeness is Completeness.COMPLETE)

    record("operational_records", _check(records_ok), "OPERATIONAL_RECORDS_UNAVAILABLE")
    record("retrieval", _check(lambda: backend == RETRIEVAL_BACKEND), "RETRIEVAL_UNAVAILABLE")

    is_ready = all(state == "ok" for state in checks.values())
    if not is_ready:
        response.status_code = 503
    return ReadinessResponse(
        status="ready" if is_ready else "not_ready",
        checks=checks,
        retrieval_backend=backend,
        version=__version__,
        errors=errors or None,
    )


# --------------------------------------------------------------------------------------
# The investigation
# --------------------------------------------------------------------------------------
def initial_state(investigation_id: str, incident: IncidentRecord) -> InvestigationState:
    """The state one investigation starts from, with its bounds already set."""
    return InvestigationState(
        investigation_id=investigation_id,
        incident=from_predefined_incident(incident),
        bounds=Bounds.starting(
            seconds=config.INVESTIGATION_DEADLINE_SECONDS,
            capability_calls=config.CAPABILITY_CALL_CAP,
            model_calls=config.MODEL_CALL_CAP,
        ),
        evidence=EvidenceSet(investigation_id=investigation_id),
    )


def _terminal(
    investigation_id: str,
    final: dict[str, Any] | None,
    failure: FailureCategory | None = None,
) -> TerminalEvent:
    """The one event that ends the stream.

    By the time this is built the record is already written, or the run failed and nothing was
    written at all. A failure carries no brief: there is nothing grounded to carry.

    The graph reports its state as a mapping of channel values, so this reads it as one rather than
    reconstructing a state object whose only use would be to be taken apart again here.
    """
    reached = final or {}
    ended_as: FailureCategory | None = failure or reached.get("failure")
    assessment = reached.get("assessment")
    if ended_as is None and assessment is not None:
        return TerminalEvent(investigation_id=investigation_id, brief=render(assessment))
    return TerminalEvent(
        investigation_id=investigation_id,
        failure=(ended_as or FailureCategory.INTERNAL_ERROR).value,
    )


async def investigation_stream(
    incident: IncidentRecord,
    disconnect: Request,
    svc: Any,
    model: Any,
    record: Any,
) -> AsyncIterator[str]:
    """One investigation, streamed as it runs.

    Async rather than a plain generator: Starlette drives a sync generator through a worker
    threadpool call per yield, and a contextvars token set before one yield cannot be reset after
    the next if that resumes on a different thread. An async generator stays on the single request
    task, so the span below safely wraps every yield.

    The graph is driven by `astream` for the same reason it must be: the synchronous `stream`
    iterates node functions on the caller's thread, which here is the event loop, so one
    investigation would hold the loop for its whole run and the process could answer nothing else
    while it lasted. `astream` runs those same sync nodes in a worker executor, leaving the loop
    free between steps.

    `disconnect` is the in-process cancellation signal, checked between steps. A client that has
    left gets nothing further, and because nothing is persisted until the graph's own save, an
    abandoned run leaves nothing behind.
    """
    investigation_id = str(uuid4())
    state = initial_state(investigation_id, incident)

    with tracing.span(
        "investigation",
        trace_id=investigation_id,
        attributes={
            "investigation_id": investigation_id,
            "incident_id": incident.incident_id,
        },
    ):
        yield IdentityEvent(investigation_id=investigation_id).model_dump_json() + "\n"

        graph_config = {
            "configurable": {MODEL: model, SERVICE: svc, RECORD: record},
            # One visit per gathering step plus the fixed nodes either side, with room for the
            # return edge. A run that would exceed this has already reached a bound.
            "recursion_limit": 2 * (config.CAPABILITY_CALL_CAP + config.MODEL_CALL_CAP) + 10,
        }

        sent = 0
        final: dict[str, Any] | None = None
        try:
            async for step in get_graph().astream(state, config=graph_config, stream_mode="values"):
                final = step
                events = step.get("events", [])
                for event in events[sent:]:
                    yield event.model_dump_json() + "\n"
                sent = len(events)
                if await disconnect.is_disconnected():
                    return
        except Exception:  # noqa: BLE001 - any unhandled fault becomes a sanitized failure
            _log.exception("investigation %s failed", investigation_id)
            yield (
                _terminal(investigation_id, None, FailureCategory.INTERNAL_ERROR).model_dump_json()
                + "\n"
            )
            return

        yield _terminal(investigation_id, final).model_dump_json() + "\n"


@app.post("/investigations")
def start_investigation(
    body: StartInvestigationRequest,
    request: Request,
    records: OperationalRecords = Depends(get_operational_records),
    svc: Any = Depends(get_service),
    model: Any = Depends(get_model),
    record: Any = Depends(get_record),
) -> StreamingResponse:
    """Start one investigation and stream it. 404 for an incident the corpus does not hold."""
    raw = records.incident(body.incident_id, deadline_s=config.SOURCE_DEADLINE_SECONDS)
    if raw is None:
        raise HTTPException(status_code=404, detail="Unknown incident_id.")
    return StreamingResponse(
        investigation_stream(IncidentRecord(**raw), request, svc, model, record),
        media_type="application/x-ndjson",
    )


# --------------------------------------------------------------------------------------
# Interaction over a completed investigation
# --------------------------------------------------------------------------------------
# Two ordinary requests over something already finished. Neither gathers evidence and neither
# creates an investigation: the record is closed, and reading it or asking about it does not
# reopen it.


class QuestionRequest(BaseModel):
    # Stripped before the length check, so whitespace alone is refused here rather than
    # spending a model call to discover there was no question.
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class AnswerResponse(BaseModel):
    """What the engineer is told, after code has checked what the Supervisor said.

    `references` are the record's own, and every one of them resolved against it. `refused` says
    the answer is this code's rather than the model's, which happens when a citation named nothing
    the record carries or a candidate position did not exist. Distinguishing the two matters: an
    engineer reading a refusal should not mistake it for the record having answered.
    """

    investigation_id: str
    answer: str
    references: list[str] = []
    candidate_position: int | None = None
    refused: bool = False


# What the engineer is told instead of an answer that cited something the record does not carry.
# The answer is replaced rather than trimmed: an answer whose support has been removed is no longer
# the answer the model gave, and presenting the remainder would be this code paraphrasing it.
_UNSUPPORTED = (
    "The answer could not be given from this record: it cited something the record does not "
    "carry. Nothing has been inferred in its place."
)


@app.get("/investigations")
def list_investigations(
    record: CompletedInvestigationRepository = Depends(get_record),
) -> list[InvestigationSummary]:
    """Every completed investigation as a summary, newest first. Each is then read in full by
    its identifier, through the route below."""
    return record.list_investigations()


@app.get("/investigations/{investigation_id}")
def read_investigation(
    investigation_id: str,
    record: CompletedInvestigationRepository = Depends(get_record),
) -> CompletedInvestigation:
    """One completed investigation, as it was saved. 404 for an identifier that names none."""
    saved = record.get(investigation_id)
    if saved is None:
        raise HTTPException(status_code=404, detail="Unknown investigation_id.")
    return saved


# --------------------------------------------------------------------------------------
# Kept evaluation runs
# --------------------------------------------------------------------------------------
# Two reads over what the evaluation runner kept, offline and under its own principal. Nothing
# here runs, triggers, or schedules an evaluation, and nothing here can write one: the
# application's identity holds read on that container and nothing more.


@app.get("/evaluations")
def list_evaluations(
    runs: EvaluationRunRepository = Depends(get_evaluation_runs),
) -> list[EvaluationRunSummary]:
    """Every kept evaluation run as a summary, newest first."""
    return runs.list_runs()


@app.get("/evaluations/{run_id}")
def read_evaluation(
    run_id: str, runs: EvaluationRunRepository = Depends(get_evaluation_runs)
) -> EvaluationRun:
    """One kept run, as it was saved. 404 for an identifier that names none."""
    saved = runs.get(run_id)
    if saved is None:
        raise HTTPException(status_code=404, detail="Unknown run_id.")
    return saved


@app.post("/investigations/{investigation_id}/questions")
def ask_about_investigation(
    investigation_id: str,
    body: QuestionRequest,
    record: CompletedInvestigationRepository = Depends(get_record),
    model: Any = Depends(get_model),
) -> AnswerResponse:
    """One question about one completed investigation, answered from that record alone.

    The Supervisor answers; code decides whether what it said stands. Every reference it cited must
    be one the record carries, and any candidate position must be a place in the assessment's
    ordered list. A failure of either replaces the answer, because the property that nothing new is
    concluded rests on the constrained context and structured references rather than on this code
    reading prose and judging it.
    """
    saved = record.get(investigation_id)
    if saved is None:
        raise HTTPException(status_code=404, detail="Unknown investigation_id.")

    proposed, _ = answer_question(model, saved, body.question)

    carried = saved.evidence_refs
    unsupported = [ref for ref in proposed.references if ref not in carried]
    position = proposed.candidate_position
    misplaced = position is not None and not (1 <= position <= len(saved.assessment.candidates))
    if unsupported or misplaced:
        _log.info(
            "answer refused for %s: %d unresolved reference(s), position %s",
            investigation_id,
            len(unsupported),
            position,
        )
        return AnswerResponse(investigation_id=investigation_id, answer=_UNSUPPORTED, refused=True)

    return AnswerResponse(
        investigation_id=investigation_id,
        answer=proposed.answer,
        references=list(proposed.references),
        candidate_position=position,
    )
