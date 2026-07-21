"""FastAPI surface — liveness, readiness, version, and the typed investigation endpoint.

Health is split three ways so an orchestrator can tell the states apart:
  - `/health/live`  — the process is running (touches nothing else). Used for liveness probes.
  - `/health/ready` — the app can actually investigate: corpus validated, repository + logs
    reachable, retrieval initialized and matching the configured backend. 503 when not.
  - `/version`       — build/runtime metadata.

The investigation endpoint returns a typed contract that represents degraded and escalated
execution honestly (it never fabricates a successful-looking report when retrieval was down) and
surfaces the safety-guardrail result. Errors never expose stack traces, local paths, or secrets.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from opspilot import __version__, config
from opspilot.checkpoint import build_checkpointer
from opspilot.composition import DiagnosisComposition, build_diagnosis
from opspilot.config import ENVIRONMENT, RETRIEVAL_BACKEND, WORKFLOW_VERSION
from opspilot.contracts import IncidentReport
from opspilot.graph import _initial_state, build_graph
from opspilot.investigations import (
    InMemoryInvestigationRepository,
    InvestigationRecord,
    InvestigationRepository,
    InvestigationStatus,
)

_UNIT_SEP = "\x1f"

app = FastAPI(title="OpsPilot", version=__version__)

# The operator console: a single self-contained, same-origin HTML page (inline CSS/JS, no external
# requests, no build step) so an operator can drive an investigation without a separate frontend
# deployment. Read once at import time — it's a packaged asset, not runtime-configurable data.
_CONSOLE_HTML = (Path(__file__).parent / "static" / "console.html").read_text(encoding="utf-8")

# One durable checkpointer per process (selected by OPSPILOT_CHECKPOINTER; `none` by default, so the
# stateless one-shot behavior is unchanged). Compiled into the graph once — when present, every
# invocation must carry a `thread_id` so the checkpoint is namespaced per investigation.
_checkpointer = build_checkpointer()
_graph = build_graph(_checkpointer)

# Composition root: one ToolService per process, injected via a FastAPI dependency so tests can
# override it with a specific backend or a deliberately-broken service. Built lazily so importing
# this module never pulls in a retrieval backend.
_tool_service = None

# One diagnosis implementation (planner + triager) per process, selected by OPSPILOT_IMPLEMENTATION
# and injected into every graph invocation alongside the ToolService. Built lazily so importing this
# module never constructs a ChatModel (single_agent) or touches an optional dependency.
_diagnosis: DiagnosisComposition | None = None


def get_service():
    global _tool_service
    if _tool_service is None:
        from opspilot.tools.service import ToolService

        _tool_service = ToolService()
    return _tool_service


def get_diagnosis() -> DiagnosisComposition:
    global _diagnosis
    if _diagnosis is None:
        _diagnosis = build_diagnosis()
    return _diagnosis


# One investigation repository per process (the async resource store). In-memory for this slice;
# a durable Cosmos-backed implementation can replace it behind the same seam. Overridable in tests.
_repository: InvestigationRepository | None = None


def get_repository() -> InvestigationRepository:
    global _repository
    if _repository is None:
        _repository = InMemoryInvestigationRepository()
    return _repository


def get_corpus_status():
    from opspilot.data.repository import validate_corpus

    return validate_corpus(config.CORPUS_DIR)


# --------------------------------------------------------------------------------------
# Contracts
# --------------------------------------------------------------------------------------
class Alert(BaseModel):
    incident_id: str | None = None
    severity: str | None = None
    category: str | None = None
    summary: str = ""


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
    # Diagnosis implementation the running process resolved to. `implementation` is the effective
    # one; `requested_implementation` + `fallback_reason` make an explicit deterministic fallback
    # visible (non-null reason ⇒ single_agent was asked for but its model could not be built).
    implementation: str = "deterministic"
    requested_implementation: str = "deterministic"
    provider: str | None = None
    model_id: str | None = None
    fallback_reason: str | None = None


class SafetyResponse(BaseModel):
    passed: bool
    violations: list[str] = Field(default_factory=list)


class ApprovalResponse(BaseModel):
    # The v1 graph auto-approves; this is labelled honestly and is NOT a human decision.
    kind: Literal["deterministic_auto_approval", "human"]
    decision: str
    approver: str


class RuntimeMetadata(BaseModel):
    retrieval_backend: str
    workflow_version: str
    application_version: str
    # The diagnosis implementation that produced THIS report (single_agent or the deterministic
    # floor), plus the model that backed it — so a consumer knows how the conclusion was reached.
    implementation: str = "deterministic"
    provider: str | None = None
    model_id: str | None = None


class InvestigationResponse(BaseModel):
    incident_id: str
    status: Literal["completed", "degraded", "escalated"]
    report: IncidentReport | None
    safety: SafetyResponse
    approval: ApprovalResponse | None
    runtime: RuntimeMetadata
    # A human-readable cause for a non-"completed" status — None when completed. Escalation carries
    # the graph's own machine-readable reason (`escalate`'s state.error); degraded is synthesized
    # here since the graph itself has no separate per-run degradation-reason field yet.
    reason: str | None = None


# --- async investigation resource --------------------------------------------------------------
class AcceptedInvestigation(BaseModel):
    """The 202 body: the minted id, its initial status, and where to poll for the result."""

    investigation_id: str
    status: InvestigationStatus
    poll_url: str


class InvestigationStatusResponse(BaseModel):
    """The polled resource — status + the ordered transition history, and the full result once
    terminal (`completed`/`degraded`/`escalated`); `error` is set instead on a `failed` run."""

    investigation_id: str
    incident_id: str
    status: InvestigationStatus
    history: list[InvestigationStatus]
    result: InvestigationResponse | None = None
    error: str | None = None


# --------------------------------------------------------------------------------------
# Operator console
# --------------------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/console")


@app.get("/console", response_class=HTMLResponse, include_in_schema=False)
def console() -> str:
    """Same-origin operator console: submit an investigation, poll it, review the result. No auth,
    no admin surface, no historical view — intentionally narrow (see docs/architecture.md §9)."""
    return _CONSOLE_HTML


# --------------------------------------------------------------------------------------
# Health / version
# --------------------------------------------------------------------------------------
@app.get("/health/live")
def live() -> LivenessResponse:
    """Liveness: the process is up. Touches no corpus, retrieval, tools, or external systems."""
    return LivenessResponse(version=__version__)


@app.get("/health")
def health() -> LivenessResponse:
    """Deprecated alias for /health/live — kept temporarily so existing probes don't break."""
    return live()


@app.get("/version")
def version(diagnosis=Depends(get_diagnosis)) -> VersionResponse:
    return VersionResponse(
        version=__version__,
        workflow_version=WORKFLOW_VERSION,
        environment=ENVIRONMENT,
        retrieval_backend=RETRIEVAL_BACKEND,
        implementation=diagnosis.implementation,
        requested_implementation=diagnosis.requested,
        provider=diagnosis.provider,
        model_id=diagnosis.model_id,
        fallback_reason=diagnosis.fallback_reason,
    )


def _check(fn) -> bool:
    """Run a readiness probe, treating any failure as a failed (never-raising) check."""
    try:
        return bool(fn())
    except Exception:  # noqa: BLE001 — readiness converts every failure into a 'failed' check
        return False


@app.get("/health/ready")
def ready(
    response: Response,
    svc=Depends(get_service),
    corpus=Depends(get_corpus_status),
) -> ReadinessResponse:
    checks: dict[str, str] = {}
    errors: list[ReadinessError] = []
    backend = _safe_backend(svc)

    def record(name: str, ok: bool, code: str) -> None:
        checks[name] = "ok" if ok else "failed"
        if not ok:
            errors.append(ReadinessError(component=name, code=code))

    def repository_ok() -> bool:
        result = svc.get_incident(incident_id="inc-004")
        return _tool_ok(result) and bool(result.results)

    def logs_ok() -> bool:
        return _tool_ok(svc.query_logs(
            service="checkout-api",
            start_time="2026-06-28T10:00:00Z", end_time="2026-06-28T11:00:00Z"))

    def retrieval_ok() -> bool:
        return (backend != "unavailable" and backend == RETRIEVAL_BACKEND
                and _tool_ok(svc.search_runbooks(query="payment timeout", k=1)))

    record("corpus", _check(lambda: corpus.ok), "CORPUS_INCOMPLETE")
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


def _tool_ok(result) -> bool:
    return getattr(result, "status", "error") == "ok"


def _safe_backend(svc) -> str:
    try:
        return str(svc.retrieval_backend)
    except Exception:  # noqa: BLE001
        return "unavailable"


# --------------------------------------------------------------------------------------
# Investigation
# --------------------------------------------------------------------------------------
def _run_and_build(alert: dict, svc, diagnosis) -> InvestigationResponse:
    """Run the graph for one alert and map its terminal state to the typed response. Shared by the
    synchronous compatibility endpoint and the async background job, so both agree exactly."""
    configurable: dict = {
        "tool_service": svc,
        "planner": diagnosis.planner,
        "triager": diagnosis.triager,
    }
    # A compiled-in checkpointer requires a thread_id to namespace the checkpoint. Each run is its
    # own thread; durable resume/interrupt over this id lands in 5c.
    if _checkpointer is not None:
        configurable["thread_id"] = f"investigate-{uuid4()}"
    state = _graph.invoke(_initial_state(alert), config={"configurable": configurable})
    backend = _safe_backend(svc)

    # Honest terminal status: an escalate carries a machine-readable error; a completed run whose
    # retrieval was unavailable is degraded (partial evidence), never a normal-looking success.
    reason: str | None = None
    if state.get("error"):
        status: Literal["completed", "degraded", "escalated"] = "escalated"
        reason = str(state["error"])
    elif backend == "unavailable":
        status = "degraded"
        reason = f"retrieval backend unavailable ({backend}); investigation ran on partial evidence"
    else:
        status = "completed"

    report_dict = state.get("report")
    report = IncidentReport.model_validate(report_dict) if report_dict else None

    safety_state = state.get("safety") or {}
    safety = SafetyResponse(
        passed=bool(safety_state.get("passed", False)),
        violations=list(safety_state.get("violations", [])),
    )

    approval = None
    approval_state = state.get("approval")
    if approval_state:
        is_stub = approval_state.get("approver") == "stub"
        approval = ApprovalResponse(
            kind="deterministic_auto_approval" if is_stub else "human",
            decision=str(approval_state.get("decision", "")),
            approver=str(approval_state.get("approver", "")),
        )

    return InvestigationResponse(
        incident_id=str(state.get("incident_id", "")),
        status=status,
        report=report,
        safety=safety,
        approval=approval,
        reason=reason,
        runtime=RuntimeMetadata(
            retrieval_backend=backend,
            workflow_version=WORKFLOW_VERSION,
            application_version=__version__,
            implementation=diagnosis.implementation,
            provider=diagnosis.provider,
            model_id=diagnosis.model_id,
        ),
    )


def _idempotency_key(alert: Alert) -> str:
    """Same derivation as the graph state's idempotency_key: (incident_id, summary). A repeat POST
    for the same incident + summary returns the existing investigation, not a duplicate run."""
    raw = _UNIT_SEP.join((alert.incident_id or "INC-STUB", alert.summary or ""))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _safe_error(exc: Exception) -> str:
    """A sanitized, class-level reason — never a stack trace, path, or secret (like readiness)."""
    return type(exc).__name__


def _run_investigation_job(
    investigation_id: str, alert: dict, *, repo: InvestigationRepository, svc, diagnosis
) -> None:
    """Background worker: drive the investigation to a terminal state, recording each transition. A
    fault in the run itself is recorded as `failed` (never a lost 202 or a surfaced 500)."""
    repo.transition(investigation_id, "running")
    try:
        response = _run_and_build(alert, svc, diagnosis)
    except Exception as exc:  # noqa: BLE001 — any run fault becomes a recorded `failed`, not a crash
        repo.transition(investigation_id, "failed", error=_safe_error(exc))
        return
    repo.transition(investigation_id, response.status, result=response.model_dump(mode="json"))


@app.post("/investigations", status_code=202)
def create_investigation(
    alert: Alert,
    response: Response,
    background: BackgroundTasks,
    svc=Depends(get_service),
    diagnosis=Depends(get_diagnosis),
    repo: InvestigationRepository = Depends(get_repository),
) -> AcceptedInvestigation:
    """The advertised contract: accept an investigation and run it in the background. Returns 202
    immediately with the minted id + a polling URL, so a client never holds a request open for the
    whole run. Idempotent on (incident_id, summary): a repeat returns the existing investigation."""
    idempotency_key = _idempotency_key(alert)
    existing = repo.find_by_idempotency_key(idempotency_key)
    if existing is not None:
        response.headers["Location"] = f"/investigations/{existing.investigation_id}"
        return AcceptedInvestigation(
            investigation_id=existing.investigation_id,
            status=existing.status,
            poll_url=f"/investigations/{existing.investigation_id}",
        )

    investigation_id = str(uuid4())
    repo.create(
        investigation_id=investigation_id,
        incident_id=alert.incident_id or "INC-STUB",
        idempotency_key=idempotency_key,
    )
    background.add_task(
        _run_investigation_job,
        investigation_id,
        alert.model_dump(),
        repo=repo,
        svc=svc,
        diagnosis=diagnosis,
    )
    response.headers["Location"] = f"/investigations/{investigation_id}"
    return AcceptedInvestigation(
        investigation_id=investigation_id,
        status="queued",
        poll_url=f"/investigations/{investigation_id}",
    )


@app.get("/investigations/{investigation_id}")
def get_investigation(
    investigation_id: str, repo: InvestigationRepository = Depends(get_repository)
) -> InvestigationStatusResponse:
    """Poll an investigation: 404 for an unknown id; otherwise the current status + ordered
    transition history, and the full typed result once terminal."""
    record: InvestigationRecord | None = repo.get(investigation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="investigation not found")
    result = InvestigationResponse.model_validate(record.result) if record.result else None
    return InvestigationStatusResponse(
        investigation_id=record.investigation_id,
        incident_id=record.incident_id,
        status=record.status,
        history=record.history,
        result=result,
        error=record.error,
    )


@app.post("/investigate")
def investigate(
    alert: Alert,
    svc=Depends(get_service),
    diagnosis=Depends(get_diagnosis),
) -> InvestigationResponse:
    """Synchronous investigation — kept as a compatibility + test endpoint. The advertised contract
    is the async resource API above (`POST /investigations` → 202, poll `GET /investigations/{id}`),
    which doesn't hold a request open for the whole run. This endpoint runs the graph inline and
    returns the full result directly."""
    return _run_and_build(alert.model_dump(), svc, diagnosis)
