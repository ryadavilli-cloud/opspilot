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
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from opspilot import __version__, config
from opspilot.auth import (
    ReviewerAuthenticator,
    ReviewerAuthError,
    ReviewerPrincipal,
    build_reviewer_authenticator,
)
from opspilot.checkpoint import build_checkpointer
from opspilot.composition import DiagnosisComposition, build_diagnosis
from opspilot.config import ENVIRONMENT, RETRIEVAL_BACKEND, WORKFLOW_VERSION
from opspilot.contracts import IncidentReport
from opspilot.graph import _initial_state, build_graph, invoke_auto_approving
from opspilot.investigations import (
    InvestigationRecord,
    InvestigationRepository,
    InvestigationStatus,
)
from opspilot.repository import build_investigation_repository

_log = logging.getLogger("opspilot.api")

_UNIT_SEP = "\x1f"
# The approver string `invoke_auto_approving` stamps on a sync-path auto-approval. It is a label
# only — nothing branches on it. `_build_response` decides `kind` from the verified `auth_method`
# instead (G-01), because a check that compared an approver *string* to this sentinel was exactly
# what let any other string present itself as human review.
_AUTO_APPROVER = "system:auto-approve"

app = FastAPI(title="OpsPilot", version=__version__)

# The operator console: a single self-contained, same-origin HTML page (inline CSS/JS, no external
# requests, no build step) so an operator can drive an investigation without a separate frontend
# deployment. Read once at import time — it's a packaged asset, not runtime-configurable data.
_CONSOLE_HTML = (Path(__file__).parent / "static" / "console.html").read_text(encoding="utf-8")

# One durable checkpointer per process (selected by OPSPILOT_CHECKPOINTER; `none` by default),
# compiled into one graph — every invocation must carry a `thread_id` so the checkpoint is
# namespaced per investigation. `build_graph` upgrades a `None` checkpointer to an in-process
# `MemorySaver()` internally — real HITL interrupts require *some* checkpointer to pause/resume at
# all — but that fallback is non-durable: an `awaiting_approval` investigation does not survive a
# process restart on it, which is why production sets `cosmos`.
#
# Built lazily, on first use, rather than at import. That is what makes the production `cosmos`
# setting safe: constructing the Cosmos saver opens a client and provisions its container, so doing
# it at import time would turn a transient Cosmos outage into a container crash-loop instead of a
# failed request on an app that is otherwise up and answering /health/live. Same reasoning, and the
# same shape, as `get_repository()` below.
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        checkpointer = build_checkpointer()
        if checkpointer is None:
            _log.warning(
                "OPSPILOT_CHECKPOINTER=none: hitl_gate interrupts pause on an in-process "
                "MemorySaver only — an awaiting_approval investigation will not survive a restart. "
                "Set sqlite/cosmos for durability."
            )
        _graph = build_graph(checkpointer)
    return _graph


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


# One investigation repository per process (the async resource store), selected by
# OPSPILOT_INVESTIGATION_REPOSITORY (`memory` by default; `cosmos` for durability across a restart /
# redeploy / multiple replicas). Built lazily, once, so importing this module never touches Cosmos.
# Overridable in tests via the FastAPI dependency.
_repository: InvestigationRepository | None = None


def get_repository() -> InvestigationRepository:
    global _repository
    if _repository is None:
        _repository = build_investigation_repository()
    return _repository


# The reviewer authenticator (G-01), built lazily and once. Lazy for the same reason as the graph
# and repository: a slow or briefly-unreachable Entra JWKS endpoint should fail the decision request
# that needs it, not crash-loop the container. Overridable in tests via the FastAPI dependency —
# which is the ONLY bypass that exists, and it exists inside the test process, not in the image.
_authenticator: ReviewerAuthenticator | None = None


def get_authenticator() -> ReviewerAuthenticator:
    global _authenticator
    if _authenticator is None:
        _authenticator = build_reviewer_authenticator()
    return _authenticator


def require_reviewer(authorization: str | None, authenticator: ReviewerAuthenticator):
    """Turn the raw Authorization header into a verified principal, or an HTTP error.

    Fail-closed: every path out of here is either a validated `ReviewerPrincipal` or an exception.
    The client-facing detail stays coarse (see `ReviewerAuthError`) while the precise cause is
    logged here, so operators can diagnose a rejected approval without the endpoint becoming an
    oracle for probing token validity.
    """
    try:
        return authenticator.authenticate(authorization)
    except ReviewerAuthError as exc:
        _log.warning(
            "reviewer authentication failed (status=%s): %s", exc.status_code, exc.reason
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc


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
    """How a decision was reached, labelled by *how the identity was proven* — never by comparing
    the approver string to a sentinel, which is what previously let a forged `approver` present
    itself as human review (G-01).

    `service_principal` exists because the deployed smoke gate must drive the decision path, and it
    authenticates as a workload. Code guidelines §15 forbids a workload identity standing in for a
    reviewer, so it gets its own honest label rather than being folded into `human`.
    """

    kind: Literal["deterministic_auto_approval", "human", "service_principal"]
    decision: str
    # Method-qualified and subject-keyed (`entra_jwt:<oid>`), not a display name — the audit trail
    # binds to the immutable object id, since display names are reassignable.
    approver: str
    # Present only for a token-backed decision: the verified tenant and the display name at the time
    # of the decision. Display name is informational and must not be used for identity comparisons.
    approver_display_name: str | None = None
    approver_tenant_id: str | None = None


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


class ConsoleAuthConfig(BaseModel):
    """The public Entra parameters the operator console needs to run a sign-in flow.

    All three are public by design — a browser-based public client has no secret to protect, and
    these values appear in the authorize URL regardless. Nothing here grants access: the token the
    flow produces is still validated server-side against Entra's keys, the configured audience, and
    the approver role before any decision is accepted.
    """

    tenant_id: str
    client_id: str
    # The scope the console requests for this API — `<audience>/.default` yields a token whose `aud`
    # matches what `EntraJwtAuthenticator` requires.
    scope: str
    # False when the deployment has no console client id configured, which the console renders as
    # "decisions unavailable here" rather than showing buttons that cannot possibly work.
    sign_in_available: bool


class InvestigationDecision(BaseModel):
    """A human's response to a paused `hitl_gate` interrupt, submitted via
    `POST /investigations/{id}/decision`. `submitted_report_hash` must match the report the
    decision was actually reviewed against — a mismatch (a concurrent edit/decision moved the
    thread first) is rejected as stale rather than silently applied to a different report.

    There is deliberately **no `approver` field** (G-01). The identity comes from the validated
    Entra token on the request and nothing else; accepting a name here and cross-checking it would
    leave a plausible-looking field that means nothing. `extra="forbid"` makes that explicit — a
    client still sending `approver` gets a 422 rather than having it silently ignored, so an
    integration built against the old shape fails loudly instead of appearing to still work.
    """

    model_config = {"extra": "forbid"}

    decision: Literal["approve", "edit", "request_more_evidence", "reject"]
    submitted_report_hash: str
    edits: dict[str, Any] | None = None


# --------------------------------------------------------------------------------------
# Operator console
# --------------------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/console")


@app.get("/console", response_class=HTMLResponse, include_in_schema=False)
def console() -> str:
    """Same-origin operator console: submit an investigation, poll it, review the result, and — once
    signed in — decide on a paused one. No admin surface, no historical view — intentionally narrow
    (see docs/architecture.md §9)."""
    return _CONSOLE_HTML


@app.get("/console/config", include_in_schema=False)
def console_config() -> ConsoleAuthConfig:
    """Sign-in parameters for the console, served rather than baked into the HTML so the page stays
    a static, cacheable asset that is identical across deployments."""
    client_id = config.ENTRA_CONSOLE_CLIENT_ID
    audience = config.ENTRA_API_AUDIENCE
    return ConsoleAuthConfig(
        tenant_id=config.ENTRA_TENANT_ID,
        client_id=client_id,
        scope=f"{audience}/.default" if audience else "",
        sign_in_available=bool(client_id and audience and config.ENTRA_TENANT_ID),
    )


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
        get_graph(), _initial_state(alert),
        config={"configurable": configurable}, approver=_AUTO_APPROVER,
    )
    return _build_response(state, svc, diagnosis)


def _build_response(state: dict, svc, diagnosis) -> InvestigationResponse:
    """Map a genuinely terminal graph state to the typed response. Shared by the sync endpoint
    (via `_run_and_build`) and the async job path (via `_advance`) — both must agree exactly."""
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
        # `kind` mirrors the verified `auth_method` stamped by the decision endpoint — it is never
        # inferred from the approver string (G-01). A decision with no `auth_method` at all can only
        # have come from the deterministic sync path, which never proves an identity, so it falls
        # back to the auto-approval label rather than to `human`: unknown provenance must degrade to
        # the weakest claim, not the strongest.
        method = approval_state.get("auth_method")
        kind: Literal["deterministic_auto_approval", "human", "service_principal"]
        if method == "entra_jwt":
            kind = "human"
        elif method == "service_principal":
            kind = "service_principal"
        else:
            kind = "deterministic_auto_approval"
        approval = ApprovalResponse(
            kind=kind,
            decision=str(approval_state.get("decision", "")),
            approver=str(approval_state.get("approver", "")),
            approver_display_name=approval_state.get("approver_display_name"),
            approver_tenant_id=approval_state.get("approver_tenant_id"),
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


def _resume_payload(decision: InvestigationDecision, principal: ReviewerPrincipal) -> dict:
    """Build the `Command(resume=...)` payload for one decision.

    Identity fields are taken from the verified principal and are not present in
    `InvestigationDecision` at all, so there is no path — not even a buggy one — by which a
    client-supplied name reaches the approval record (G-01). `hitl_gate` consumes exactly these
    keys.
    """
    return {
        "decision": decision.decision,
        "submitted_report_hash": decision.submitted_report_hash,
        "edits": decision.edits,
        "approver": principal.audit_label(),
        "approver_display_name": principal.display_name,
        "approver_tenant_id": principal.tenant_id,
        "auth_method": principal.auth_method,
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
        lambda: get_graph().invoke(initial, config=config),
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
        lambda: get_graph().invoke(Command(resume=decision), config=config),
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
    authorization: str | None = Header(default=None),
    svc=Depends(get_service),
    diagnosis=Depends(get_diagnosis),
    repo: InvestigationRepository = Depends(get_repository),
    authenticator: ReviewerAuthenticator = Depends(get_authenticator),
) -> AcceptedInvestigation:
    """Submit a reviewer's decision on a paused investigation and resume it in the background.

    401/403 for an unproven or unauthorized identity; 404 for an unknown id; 409 if the
    investigation isn't currently `awaiting_approval` — all validated synchronously so a rejected
    or wrong-status submission never silently no-ops in the background.

    **Authentication runs first, before the record is even looked up.** Order matters: probing this
    endpoint without a valid token must not reveal which investigation ids exist, so an anonymous
    caller cannot tell 404 from 409 from a real pause.
    """
    principal = require_reviewer(authorization, authenticator)

    record = repo.get(investigation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="investigation not found")
    if record.status != "awaiting_approval":
        raise HTTPException(
            status_code=409,
            detail=f"investigation is not awaiting a decision (status={record.status})",
        )

    # The resume payload is assembled HERE, server-side, from the validated body plus the verified
    # principal — the client contributes the decision and the hash it reviewed, never the identity.
    resume = _resume_payload(decision, principal)

    _log.info(
        "decision %s on %s by %s (kind=%s)",
        decision.decision, investigation_id, principal.audit_label(), principal.auth_method,
    )

    # The only place this transition happens for a resume — _resume_investigation_job must not
    # repeat it, or history would show a spurious duplicate "running" entry.
    repo.transition(investigation_id, "running")
    background.add_task(
        _resume_investigation_job,
        investigation_id,
        resume,
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
