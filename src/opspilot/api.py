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
import logging
from typing import Any, Literal
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from opspilot import __version__, config
from opspilot.checkpoint import build_checkpointer
from opspilot.composition import DiagnosisComposition, build_diagnosis
from opspilot.config import ENVIRONMENT, RETRIEVAL_BACKEND, WORKFLOW_VERSION
from opspilot.contracts import IncidentReport
from opspilot.graph import _initial_state, build_graph, invoke_auto_approving
from opspilot.investigations import (
    InMemoryInvestigationRepository,
    InvestigationRecord,
    InvestigationRepository,
    InvestigationStatus,
)

_log = logging.getLogger("opspilot.api")

_UNIT_SEP = "\x1f"
# The approver string `invoke_auto_approving` stamps on a sync-path auto-approval — kept as a
# single constant so `_build_response`'s "is this a real human?" check matches exactly.
_AUTO_APPROVER = "system:auto-approve"

app = FastAPI(title="OpsPilot", version=__version__)

# One durable checkpointer per process (selected by OPSPILOT_CHECKPOINTER; `none` by default).
# `build_graph` upgrades a `None` checkpointer to an in-process `MemorySaver()` internally — real
# HITL interrupts require *some* checkpointer to pause/resume at all — but that fallback is
# non-durable: an `awaiting_approval` investigation does not survive a process restart on it.
_checkpointer = build_checkpointer()
if _checkpointer is None:
    _log.warning(
        "OPSPILOT_CHECKPOINTER=none: hitl_gate interrupts pause on an in-process MemorySaver only "
        "— an awaiting_approval investigation will not survive a restart. Set sqlite/cosmos for "
        "durability."
    )
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


# --- async investigation resource --------------------------------------------------------------
class AcceptedInvestigation(BaseModel):
    """The 202 body: the minted id, its initial status, and where to poll for the result."""

    investigation_id: str
    status: InvestigationStatus
    poll_url: str


class InvestigationStatusResponse(BaseModel):
    """The polled resource — status + the ordered transition history, and the full result once
    terminal (`completed`/`degraded`/`escalated`); `error` is set instead on a `failed` run.
    `pending_decision` carries the report/hash/hypothesis awaiting a human decision while
    `status == "awaiting_approval"`."""

    investigation_id: str
    incident_id: str
    status: InvestigationStatus
    history: list[InvestigationStatus]
    result: InvestigationResponse | None = None
    error: str | None = None
    pending_decision: dict[str, Any] | None = None


class InvestigationDecision(BaseModel):
    """A human's response to a paused `hitl_gate` interrupt, submitted via
    `POST /investigations/{id}/decision`. `submitted_report_hash` must match the report the
    decision was actually reviewed against — a mismatch (a concurrent edit/decision moved the
    thread first) is rejected as stale rather than silently applied to a different report."""

    decision: Literal["approve", "edit", "request_more_evidence", "reject"]
    approver: str
    submitted_report_hash: str
    edits: dict[str, Any] | None = None


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
    """Run the graph for one alert to a genuinely terminal state — auto-approving any `hitl_gate`
    pause along the way — and map it to the typed response. Used only by the synchronous
    `/investigate` compatibility endpoint, which has always returned a complete result inline; the
    async job API below must NOT auto-approve, so it does not call this."""
    configurable: dict = {
        "tool_service": svc,
        "planner": diagnosis.planner,
        "triager": diagnosis.triager,
        "thread_id": f"investigate-{uuid4()}",
    }
    state = invoke_auto_approving(
        _graph, _initial_state(alert),
        config={"configurable": configurable}, approver=_AUTO_APPROVER,
    )
    return _build_response(state, svc, diagnosis)


def _build_response(state: dict, svc, diagnosis) -> InvestigationResponse:
    """Map a genuinely terminal graph state to the typed response. Shared by the sync endpoint
    (via `_run_and_build`) and the async job path (via `_advance`) — both must agree exactly."""
    backend = _safe_backend(svc)

    # Honest terminal status: an escalate carries a machine-readable error; a completed run whose
    # retrieval was unavailable is degraded (partial evidence), never a normal-looking success.
    if state.get("error"):
        status: Literal["completed", "degraded", "escalated"] = "escalated"
    elif backend == "unavailable":
        status = "degraded"
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
        is_stub = approval_state.get("approver") == _AUTO_APPROVER
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
    """(incident_id, summary, WORKFLOW_VERSION): a repeat POST for the same incident + summary
    returns the existing investigation, not a duplicate run — but a workflow/model version bump
    mints a fresh one instead of returning a run produced under the old version forever.
    Deliberately NOT the same derivation as the graph state's own `idempotency_key` (`ingest()`,
    unversioned) — that one identifies a re-entrant graph turn; this one an API resource."""
    raw = _UNIT_SEP.join((alert.incident_id or "INC-STUB", alert.summary or "", WORKFLOW_VERSION))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _safe_error(exc: Exception) -> str:
    """A sanitized, class-level reason — never a stack trace, path, or secret (like readiness)."""
    return type(exc).__name__


def _advance(
    investigation_id: str, run, *, repo: InvestigationRepository, svc, diagnosis
) -> None:
    """Run `run()` (an initial invoke or a decision resume) and record the outcome: a paused
    `hitl_gate` interrupt becomes `awaiting_approval` with the pending report attached — NOT a
    completed run — anything else genuinely terminal is mapped and recorded as usual. Shared by
    the initial job and every decision-resume, so a real reviewer never has a paused run
    misreported as `completed`, and an `edit` decision that re-interrupts is handled the same way
    as the first pause."""
    try:
        state = run()
    except Exception as exc:  # noqa: BLE001 — any run fault becomes a recorded `failed`, not a crash
        repo.transition(investigation_id, "failed", error=_safe_error(exc))
        return
    pending = state.get("__interrupt__")
    if pending:
        repo.transition(investigation_id, "awaiting_approval", pending_interrupt=pending[0].value)
        return
    response = _build_response(state, svc, diagnosis)
    repo.transition(investigation_id, response.status, result=response.model_dump(mode="json"))


def _configurable_for(investigation_id: str, *, svc, diagnosis) -> dict:
    """The LangGraph `configurable` for one investigation — `thread_id` is the investigation's own
    id, so the checkpoint namespace, the poll id, and `state.investigation_id` are one string."""
    return {
        "tool_service": svc,
        "planner": diagnosis.planner,
        "triager": diagnosis.triager,
        "thread_id": investigation_id,
    }


def _run_investigation_job(
    investigation_id: str, alert: dict, *, repo: InvestigationRepository, svc, diagnosis
) -> None:
    """Background worker: drive a fresh investigation to its first terminal state or pause,
    recording each transition."""
    repo.transition(investigation_id, "running")
    config = {"configurable": _configurable_for(investigation_id, svc=svc, diagnosis=diagnosis)}
    initial = _initial_state(alert, investigation_id=investigation_id)
    _advance(
        investigation_id,
        lambda: _graph.invoke(initial, config=config),
        repo=repo, svc=svc, diagnosis=diagnosis,
    )


def _resume_investigation_job(
    investigation_id: str, decision: dict, *, repo: InvestigationRepository, svc, diagnosis
) -> None:
    """Background worker: resume a paused investigation with a human decision. An `edit` naturally
    re-enters `awaiting_approval` with a NEW pending report (via `_advance`'s interrupt check) —
    no special-casing needed here."""
    from langgraph.types import Command

    config = {"configurable": _configurable_for(investigation_id, svc=svc, diagnosis=diagnosis)}
    _advance(
        investigation_id,
        lambda: _graph.invoke(Command(resume=decision), config=config),
        repo=repo, svc=svc, diagnosis=diagnosis,
    )


@app.post("/investigations", status_code=202)
def create_investigation(
    alert: Alert,
    response: Response,
    background: BackgroundTasks,
    force_rerun: bool = False,
    svc=Depends(get_service),
    diagnosis=Depends(get_diagnosis),
    repo: InvestigationRepository = Depends(get_repository),
) -> AcceptedInvestigation:
    """The advertised contract: accept an investigation and run it in the background. Returns 202
    immediately with the minted id + a polling URL, so a client never holds a request open for the
    whole run. Idempotent on (incident_id, summary, workflow version): a repeat returns the existing
    investigation, atomically — `repo.get_or_create` closes the race where two concurrent identical
    POSTs could each see "not found" and both start a run. Pass `?force_rerun=true` to mint a fresh
    investigation for the same key anyway (a reopened incident, new telemetry, an operator-requested
    retry); the superseded investigation stays reachable by its own id, but a later non-forced POST
    for the same key now returns the rerun instead of it."""
    idempotency_key = _idempotency_key(alert)
    investigation_id = str(uuid4())
    record, created = repo.get_or_create(
        idempotency_key=idempotency_key,
        investigation_id=investigation_id,
        incident_id=alert.incident_id or "INC-STUB",
        thread_id=investigation_id,
        force_rerun=force_rerun,
    )
    if created:
        background.add_task(
            _run_investigation_job,
            record.investigation_id,
            alert.model_dump(),
            repo=repo,
            svc=svc,
            diagnosis=diagnosis,
        )
    response.headers["Location"] = f"/investigations/{record.investigation_id}"
    return AcceptedInvestigation(
        investigation_id=record.investigation_id,
        status=record.status,
        poll_url=f"/investigations/{record.investigation_id}",
    )


@app.post("/investigations/{investigation_id}/decision", status_code=202)
def submit_decision(
    investigation_id: str,
    decision: InvestigationDecision,
    background: BackgroundTasks,
    svc=Depends(get_service),
    diagnosis=Depends(get_diagnosis),
    repo: InvestigationRepository = Depends(get_repository),
) -> AcceptedInvestigation:
    """Submit a human's decision on a paused investigation and resume it in the background. 404 for
    an unknown id; 409 if the investigation isn't currently `awaiting_approval` — validated
    synchronously so a wrong-status submission never silently no-ops in the background."""
    record = repo.get(investigation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="investigation not found")
    if record.status != "awaiting_approval":
        raise HTTPException(
            status_code=409,
            detail=f"investigation is not awaiting a decision (status={record.status})",
        )
    # The only place this transition happens for a resume — _resume_investigation_job must not
    # repeat it, or history would show a spurious duplicate "running" entry.
    repo.transition(investigation_id, "running")
    background.add_task(
        _resume_investigation_job,
        investigation_id,
        decision.model_dump(),
        repo=repo,
        svc=svc,
        diagnosis=diagnosis,
    )
    return AcceptedInvestigation(
        investigation_id=investigation_id,
        status="running",
        poll_url=f"/investigations/{investigation_id}",
    )


@app.get("/investigations/{investigation_id}")
def get_investigation(
    investigation_id: str, repo: InvestigationRepository = Depends(get_repository)
) -> InvestigationStatusResponse:
    """Poll an investigation: 404 for an unknown id; otherwise the current status + ordered
    transition history, the full typed result once terminal, and the pending report/hash awaiting
    a decision while paused (`status == "awaiting_approval"`)."""
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
        pending_decision=record.pending_interrupt,
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
