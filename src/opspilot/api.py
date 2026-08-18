"""The HTTP surface: health, version, the screen, and one streaming investigation.

Health is split three ways so an orchestrator can tell the states apart:
  - `/health/live`   the process is running, touching nothing else
  - `/health/ready`  the application can actually investigate: the operational-records container
                     holds every record kind, incident and log lookups answer, retrieval is
                     initialized and matches the configured backend. 503 when not
  - `/version`       build and runtime metadata

`POST /investigations` is the only investigative route. One live streaming request owns one
investigation: identity first, then activity as it happens, then exactly one terminal event
carrying the brief or a sanitized failure category. There is no job, no polling, and no resumption.
If the request disconnects the run is abandoned, which is safe precisely because the record is
written before the terminal event or not at all.

Errors never expose a stack trace, a path, or a secret.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel

from opspilot import __version__, config
from opspilot.assessment.brief import render
from opspilot.config import ENVIRONMENT, RETRIEVAL_BACKEND, WORKFLOW_VERSION
from opspilot.data.operational_records import (
    RECORD_KINDS,
    OperationalRecords,
    PreparationStatus,
    default_operational_records,
    preparation_status,
)
from opspilot.evidence.operations import EvidenceSet
from opspilot.intake.contracts import from_predefined_incident
from opspilot.investigation.graph import MODEL, RECORD, SERVICE, build_graph
from opspilot.investigation.state import Bounds, FailureCategory, InvestigationState
from opspilot.obs import tracing
from opspilot.record.memory import InMemoryInvestigationRecord
from opspilot.stream.contracts import IdentityEvent, TerminalEvent
from opspilot.tools.contracts import Completeness, IncidentRecord

_log = logging.getLogger("opspilot.api")

app = FastAPI(title="OpsPilot", version=__version__)

# The one-screen client: a self-contained, same-origin page with no build step, read once at import
# because it is a packaged asset rather than runtime-configurable data.
_INVESTIGATION_HTML = (Path(__file__).parent / "static" / "investigation.html").read_text(
    encoding="utf-8"
)

# Every lazy singleton below is built under this lock. `if x is None: x = build()` is a
# check-then-act race: two concurrent first requests both observe None and both construct, which
# for the graph would mean two compiled graphs and for the record two separate stores.
_singleton_lock = threading.Lock()

_graph: Any = None
_tool_service: Any = None
_model: Any = None
_record: InMemoryInvestigationRecord | None = None
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


def get_record() -> InMemoryInvestigationRecord:
    global _record
    if _record is None:
        with _singleton_lock:
            if _record is None:
                _record = InMemoryInvestigationRecord()
    return _record


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


def get_records_status(
    records: OperationalRecords = Depends(get_operational_records),
) -> PreparationStatus:
    """Whether corpus preparation has run against the container this application reads.

    Fails closed: a container that cannot answer reports every kind missing rather than raising,
    because a dependency that raised would answer the probe with a 500 and lose the distinction
    readiness exists to draw.
    """
    try:
        return preparation_status(records, deadline_s=config.SOURCE_DEADLINE_SECONDS)
    except Exception:  # noqa: BLE001 - readiness converts every failure into a failed check
        return PreparationStatus(counts={}, missing=RECORD_KINDS)


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
    workflow_version: str
    version: str
    errors: list[ReadinessError] | None = None


class VersionResponse(BaseModel):
    application: str = "opspilot"
    version: str
    workflow_version: str
    environment: str
    retrieval_backend: str


# --------------------------------------------------------------------------------------
# Screen
# --------------------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/investigation")


@app.get("/investigation", response_class=HTMLResponse, include_in_schema=False)
def investigation() -> str:
    """Intake, a compact live activity feed, the brief as the dominant element once it arrives,
    and one expandable details area."""
    return _INVESTIGATION_HTML


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
        workflow_version=WORKFLOW_VERSION,
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
def ready(
    response: Response,
    svc: Any = Depends(get_service),
    records: PreparationStatus = Depends(get_records_status),
) -> ReadinessResponse:
    checks: dict[str, str] = {}
    errors: list[ReadinessError] = []
    backend = _safe_backend(svc)

    def record(name: str, ok: bool, code: str) -> None:
        checks[name] = "ok" if ok else "failed"
        if not ok:
            errors.append(ReadinessError(component=name, code=code))

    def repository_ok() -> bool:
        # This check wants the seed incident actually present, so it reads completeness too: a
        # reachable but unseeded container answers succeeded with empty, which is a true answer to
        # the query and still not a ready deployment.
        result = svc.get_incident(incident_id="inc-004")
        return bool(result.answered and result.completeness is Completeness.COMPLETE)

    def logs_ok() -> bool:
        # Readiness asks only whether the source answered. A window holding no logs is succeeded
        # with empty, a healthy source reporting nothing rather than a failure.
        return bool(
            svc.query_logs(
                service="checkout-api",
                start_time="2026-06-28T10:00:00Z",
                end_time="2026-06-28T11:00:00Z",
            ).answered
        )

    def retrieval_ok() -> bool:
        return bool(
            backend != "unavailable"
            and backend == RETRIEVAL_BACKEND
            and svc.search_runbooks(query="payment timeout", k=1).answered
        )

    record("operational_records", _check(lambda: records.ok), "OPERATIONAL_RECORDS_INCOMPLETE")
    record("repository", _check(repository_ok), "REPOSITORY_LOOKUP_FAILED")
    record("logs", _check(logs_ok), "LOG_QUERY_FAILED")
    record("retrieval", _check(retrieval_ok), "RETRIEVAL_INITIALIZATION_FAILED")

    is_ready = all(state == "ok" for state in checks.values())
    if not is_ready:
        response.status_code = 503
    return ReadinessResponse(
        status="ready" if is_ready else "not_ready",
        checks=checks,
        retrieval_backend=backend,
        workflow_version=WORKFLOW_VERSION,
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
        final: InvestigationState | None = None
        try:
            for step in get_graph().stream(state, config=graph_config, stream_mode="values"):
                final = step if isinstance(step, InvestigationState) else final
                if final is None:
                    continue
                for event in final.events[sent:]:
                    yield event.model_dump_json() + "\n"
                sent = len(final.events)
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
