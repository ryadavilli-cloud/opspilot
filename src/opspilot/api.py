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

from typing import Literal

from fastapi import Depends, FastAPI, Response
from pydantic import BaseModel, Field

from opspilot import __version__, config
from opspilot.composition import DiagnosisComposition, build_diagnosis
from opspilot.config import ENVIRONMENT, RETRIEVAL_BACKEND, WORKFLOW_VERSION
from opspilot.contracts import IncidentReport
from opspilot.graph import _initial_state, build_graph

app = FastAPI(title="OpsPilot", version=__version__)
_graph = build_graph()

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
@app.post("/investigate")
def investigate(
    alert: Alert,
    svc=Depends(get_service),
    diagnosis=Depends(get_diagnosis),
) -> InvestigationResponse:
    state = _graph.invoke(
        _initial_state(alert.model_dump()),
        config={"configurable": {
            "tool_service": svc,
            "planner": diagnosis.planner,
            "triager": diagnosis.triager,
        }},
    )
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
        runtime=RuntimeMetadata(
            retrieval_backend=backend,
            workflow_version=WORKFLOW_VERSION,
            application_version=__version__,
            implementation=diagnosis.implementation,
            provider=diagnosis.provider,
            model_id=diagnosis.model_id,
        ),
    )
