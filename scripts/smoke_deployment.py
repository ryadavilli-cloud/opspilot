"""Post-deploy smoke test — exercises the real OpsPilot investigation workflow against a live
deployment, not just process liveness. Deserializes every response into the same Pydantic
models the API uses, so a schema drift between this script and the API fails loudly.

Usage: uv run python scripts/smoke_deployment.py <base-url>
       (or set OPSPILOT_BASE_URL instead of the positional argument)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import httpx
from pydantic import ValidationError

from opspilot.api import (
    AcceptedInvestigation,
    InvestigationResponse,
    ReadinessResponse,
    VersionResponse,
)

# inc-004: a fixed, answer-keyed incident (data/answer_key/scenarios.yaml) — same fixture
# used by tests/test_api.py::test_investigation_smoke_path_over_bm25.
# Every terminal state the investigation endpoint can report. The smoke asserts the deployment
# reached one of them coherently, not which one: that choice belongs to the model.
TERMINAL_STATUSES = frozenset({"completed", "degraded", "escalated"})

SMOKE_INCIDENT_ID = "inc-004"
SMOKE_INCIDENT_SUMMARY = "checkout-api returning 500s shortly after this morning's deployment."
REQUEST_TIMEOUT_S = 10.0
# The synchronous /investigate runs a FULL multi-call LLM investigation before it responds, so it
# needs far more than the 10s default that suits /health and /version — especially with a reasoning
# model (gpt-5-mini) whose calls are slow. A too-short timeout reads as a ReadTimeout that looks
# like a hang but is just the client giving up mid-investigation.
INVESTIGATE_TIMEOUT_S = 180.0
MAX_POLL_INTERVAL_S = 20.0


class SmokeTestFailure(RuntimeError):
    """Raised when a deployed OpsPilot instance fails the smoke-test contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeTestFailure(message)


def wait_for_ready(
    client: httpx.Client, *, timeout_s: float, poll_interval_s: float
) -> ReadinessResponse:
    deadline = time.monotonic() + timeout_s
    attempt = 0
    last_error = "no attempts made"
    while time.monotonic() < deadline:
        attempt += 1
        try:
            resp = client.get("/health/ready")
        except httpx.HTTPError as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            print(
                f"[smoke] readiness attempt {attempt}: request failed ({last_error}) — retrying",
                flush=True,
            )
        else:
            body = ReadinessResponse.model_validate(resp.json())
            print(
                f"[smoke] readiness attempt {attempt}: HTTP {resp.status_code} "
                f"status={body.status} checks={body.checks} backend={body.retrieval_backend}",
                flush=True,
            )
            if resp.status_code == 200 and body.status == "ready":
                return body
            last_error = f"status={body.status} checks={body.checks} errors={body.errors}"
        sleep_for = min(poll_interval_s * (1.5 ** min(attempt - 1, 4)), MAX_POLL_INTERVAL_S)
        time.sleep(sleep_for)
    raise SmokeTestFailure(
        f"/health/ready did not report ready within {timeout_s:.0f}s "
        f"(attempt #{attempt}, last observation: {last_error})"
    )


def check_version(client: httpx.Client) -> VersionResponse:
    resp = client.get("/version")
    _require(
        resp.status_code == 200, f"/version returned HTTP {resp.status_code}: {resp.text[:500]}"
    )
    version = VersionResponse.model_validate(resp.json())
    _require(
        version.retrieval_backend == "bm25",
        f"/version reports backend {version.retrieval_backend!r}, expected 'bm25' "
        "(deployed image forces bm25)",
    )
    # The whole point of this deploy: Azure must be running the real LLM agent, not the floor. A
    # non-null fallback_reason means single_agent was requested but its model could not be built.
    _require(
        version.implementation == "single_agent",
        f"/version reports implementation {version.implementation!r} (requested "
        f"{version.requested_implementation!r}); expected 'single_agent'. "
        f"fallback_reason={version.fallback_reason!r}",
    )
    _require(
        version.provider == "azure",
        f"/version reports provider {version.provider!r}, expected 'azure'",
    )
    _require(
        bool(version.model_id),
        "/version reports no model_id, but single_agent must name its Azure deployment",
    )
    print(
        f"[smoke] version: application={version.application} version={version.version} "
        f"workflow_version={version.workflow_version} environment={version.environment} "
        f"implementation={version.implementation} provider={version.provider} "
        f"model_id={version.model_id}",
        flush=True,
    )
    return version


def run_investigation(client: httpx.Client, auth: dict[str, str]) -> InvestigationResponse:
    # The ingress gate, checkable on every deploy: an anonymous caller must not be able to spend
    # model budget on the sync route either (G-03). Mirrors the unauthenticated-decision check.
    anon = client.post(
        "/investigate", json={"incident_id": SMOKE_INCIDENT_ID, "summary": "anon probe"}
    )
    _require(
        anon.status_code == 401,
        f"unauthenticated /investigate returned HTTP {anon.status_code}, expected 401; public "
        f"ingress is still open on the synchronous route",
    )

    resp = client.post(
        "/investigate",
        headers=auth,
        json={"incident_id": SMOKE_INCIDENT_ID, "summary": SMOKE_INCIDENT_SUMMARY},
        timeout=INVESTIGATE_TIMEOUT_S,
    )
    _require(
        resp.status_code != 403,
        f"/investigate returned 403 for the smoke principal: {resp.text[:300]}. The deploy "
        f"service principal needs the submit app role granted in Entra. It holds only the "
        f"approver role from the G-01 bootstrap, which predates the submit role.",
    )
    _require(
        resp.status_code == 200,
        f"/investigate returned HTTP {resp.status_code}: {resp.text[:500]}",
    )
    investigation = InvestigationResponse.model_validate(resp.json())

    # WHICH terminal state a run reaches is model-decided, not a property of the deployment. The
    # sufficiency gate is driven by a reasoning model that accepts neither temperature nor seed, so
    # the same incident completes on one run and escalates on the next. Asserting "completed" made
    # this gate fail randomly against correct behaviour. What the smoke can honestly assert is that
    # the deployment ran an investigation to SOME terminal state and reported it coherently.
    # Whether the diagnosis was good enough to conclude is an evaluation question, and evaluation
    # is offline and advisory by design.
    _require(
        investigation.status in TERMINAL_STATUSES,
        f"investigation status={investigation.status!r}, expected one of "
        f"{sorted(TERMINAL_STATUSES)}",
    )

    report = investigation.report
    if investigation.status == "completed":
        _require(report is not None, "investigation completed but report is None")
        assert report is not None  # narrows for the type checker after _require
        _require(bool(report.evidence), "investigation report has no evidence")
        _require(bool(report.citations), "investigation report has no citations")
        _require(
            investigation.safety.passed, f"safety checks failed: {investigation.safety.violations}"
        )
        _require(
            investigation.approval is not None
            and investigation.approval.kind == "deterministic_auto_approval",
            f"expected deterministic_auto_approval, got approval={investigation.approval}",
        )
    else:
        # A non-completed terminal state must still be self-explaining: a run that stops without
        # saying why is a real defect, distinct from one that stops for a legitimate reason.
        _require(
            bool(investigation.reason),
            f"investigation ended {investigation.status!r} with no reason given",
        )
    _require(
        investigation.runtime.retrieval_backend == "bm25",
        f"investigation ran against backend {investigation.runtime.retrieval_backend!r}, "
        "expected 'bm25'",
    )
    # Prove THIS investigation was produced by the LLM agent on Azure, not the deterministic floor.
    _require(
        investigation.runtime.implementation == "single_agent",
        f"investigation ran implementation {investigation.runtime.implementation!r}, "
        "expected 'single_agent'",
    )
    _require(
        investigation.runtime.provider == "azure",
        f"investigation ran provider {investigation.runtime.provider!r}, expected 'azure'",
    )

    detail = (
        f"hypothesis={report.hypothesis!r} evidence={len(report.evidence)} "
        f"citations={len(report.citations)}"
        if report is not None
        else f"reason={investigation.reason!r}"
    )
    print(
        f"[smoke] investigation: incident_id={investigation.incident_id} "
        f"status={investigation.status} implementation={investigation.runtime.implementation} "
        f"provider={investigation.runtime.provider} model_id={investigation.runtime.model_id} "
        f"{detail}",
        flush=True,
    )
    return investigation


def _reviewer_token(audience: str) -> str:
    """A reviewer bearer token for the decision endpoint, acquired as the deploy service principal
    via the already-authenticated `az` CLI. This is a WORKLOAD identity — the API accepts it but
    stamps `kind: service_principal`, never `human` (G-01, code guidelines §15). It works only once
    the app registration exists and this SP has been granted the approver role (see the ADR).

    `--scope <audience>/.default` (not `--resource`) so the token matches what the API validates: a
    v2.0 token whose `aud` is the API's app id. `audience` is that app id."""
    try:
        out = subprocess.run(
            ["az", "account", "get-access-token", "--scope", f"{audience}/.default", "-o", "json"],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise SmokeTestFailure(
            f"could not acquire a reviewer token for {audience!r}: {detail}"
        ) from exc
    token = json.loads(out.stdout).get("accessToken")
    _require(bool(token), "az returned no accessToken")
    return token


def _smoke_auth_headers() -> dict[str, str]:
    """The Authorization header every investigation leg now needs, acquired once per run.

    An unset `OPSPILOT_SMOKE_AUDIENCE` is now FATAL rather than a warning. It used to mean only
    "skip the decision leg", because submit, poll, and the sync route were all anonymous. Since the
    ingress-auth slice closed those, a run without a token can exercise nothing beyond `/health`
    and `/version`, and passing the deploy on health alone is precisely the gate-that-is-not-a-gate
    that code guidelines §2 forbids. Fail here instead, with the fix named.
    """
    audience = os.environ.get("OPSPILOT_SMOKE_AUDIENCE", "").strip()
    if not audience:
        raise SmokeTestFailure(
            "OPSPILOT_SMOKE_AUDIENCE is unset, so no reviewer token can be acquired. Every "
            "investigation route now requires a proven principal, so this run could only check "
            "/health and /version, which is not a release gate. Set the repo variable to the "
            "Entra API audience (see the reviewer-identity ADR)."
        )
    return {"Authorization": f"Bearer {_reviewer_token(audience)}"}


def run_async_investigation(client: httpx.Client, auth: dict[str, str]) -> None:
    """Exercises the async job API end to end — the real hitl_gate pause, the Cosmos-backed
    InvestigationRepository, and (when configured) the authenticated decision endpoint (G-01).

    `force_rerun` is required: this smoke test always posts the same fixed incident, and without
    it a repeat deploy would just observe the previous run's already-completed investigation,
    proving nothing new.

    Every leg here is authenticated: submit, poll, and decide all require a proven principal since
    the ingress-auth slice. The token is the deploy service principal's, acquired once in `main`;
    the API stamps it `service_principal`, never `human` (G-01, code guidelines §15)."""
    anon = client.post(
        "/investigations",
        params={"force_rerun": "true"},
        json={"incident_id": SMOKE_INCIDENT_ID, "summary": "anon probe"},
    )
    _require(
        anon.status_code == 401,
        f"unauthenticated POST /investigations returned HTTP {anon.status_code}, expected 401",
    )

    resp = client.post(
        "/investigations",
        headers=auth,
        params={"force_rerun": "true"},
        json={"incident_id": SMOKE_INCIDENT_ID, "summary": SMOKE_INCIDENT_SUMMARY},
    )
    _require(
        resp.status_code != 403,
        f"POST /investigations returned 403 for the smoke principal: {resp.text[:300]}. Grant the "
        f"deploy service principal the submit app role in Entra.",
    )
    _require(
        resp.status_code == 202,
        f"POST /investigations returned HTTP {resp.status_code}: {resp.text[:500]}",
    )
    accepted = AcceptedInvestigation.model_validate(resp.json())

    # This leg stops here deliberately. What used to follow (poll to `awaiting_approval`, submit an
    # authenticated approval, resume, assert `completed`) asserted the human-approval surface: a
    # pause between synthesis and delivery, a decision endpoint, and a resume. The accepted design
    # has no approval stage at all, so those assertions test behavior the target system must not
    # have, and holding a deploy gate to them fails correct behavior.
    #
    # It was also irreducibly flaky. Reaching `awaiting_approval` requires the diagnosis loop to
    # satisfy the deterministic sufficiency gate first; when the planner exhausts its plan short of
    # that, the graph legitimately routes to `escalated` instead. The deployed model is a reasoning
    # model that takes neither `temperature` nor `seed`, so two runs of the same incident minutes
    # apart genuinely differ, and inc-004 is one of the deliberately ambiguous scenarios.
    #
    # What is kept is every property that is both deterministic and still true of the target: an
    # anonymous submit is refused, an authenticated submit is accepted, and an anonymous decision
    # is refused. The synchronous leg above already proves the deployed app completes a real
    # investigation against the real model, so nothing about "does it actually work" is lost.
    #
    # An unauthenticated decision MUST be refused, and this does not need a real pending decision
    # to check: `submit_decision` authenticates before it looks the record up, deliberately, so
    # that probing cannot reveal which investigation ids exist. The 401 therefore holds whatever
    # state the investigation is in, which is what makes this assertion deterministic.
    #
    # The body must still be WELL FORMED, which is a separate ordering from the one above. FastAPI
    # validates the request body before the handler runs at all, so a body missing a required field
    # returns 422 and the auth check never executes. `InvestigationDecision` requires `decision_id`
    # and forbids extra fields, so an incomplete probe would test Pydantic rather than the gate.
    anon_decision = client.post(
        f"{accepted.poll_url}/decision",
        json={
            "decision_id": "smoke-unauthenticated-probe",
            "decision": "approve",
            "submitted_report_hash": "unauthenticated-probe",
        },
    )
    _require(
        anon_decision.status_code == 401,
        f"unauthenticated decision returned HTTP {anon_decision.status_code}, expected 401; the "
        f"decision endpoint is not enforcing caller identity",
    )
    print(
        f"[smoke] async submit accepted and both ingress gates enforced: "
        f"investigation_id={accepted.investigation_id}",
        flush=True,
    )


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    base_url = argv[0] if argv else os.environ.get("OPSPILOT_BASE_URL")
    if not base_url:
        print("usage: smoke_deployment.py <base-url>  (or set OPSPILOT_BASE_URL)", file=sys.stderr)
        return 2

    ready_timeout_s = float(os.environ.get("OPSPILOT_SMOKE_READY_TIMEOUT_S", "300"))
    poll_interval_s = float(os.environ.get("OPSPILOT_SMOKE_POLL_INTERVAL_S", "5"))

    print(f"[smoke] target: {base_url}", flush=True)
    try:
        with httpx.Client(base_url=base_url.rstrip("/"), timeout=REQUEST_TIMEOUT_S) as client:
            ready = wait_for_ready(
                client, timeout_s=ready_timeout_s, poll_interval_s=poll_interval_s
            )
            _require(ready.checks.get("corpus") == "ok", f"corpus check not ok: {ready.checks}")
            _require(
                ready.checks.get("repository") == "ok",
                f"repository check not ok: {ready.checks}",
            )
            _require(
                ready.retrieval_backend == "bm25",
                f"expected bm25 retrieval backend at readiness, got {ready.retrieval_backend!r}",
            )
            check_version(client)
            auth = _smoke_auth_headers()
            run_investigation(client, auth)
            run_async_investigation(client, auth)
    except SmokeTestFailure as exc:
        print(f"[smoke] FAIL — {exc}", file=sys.stderr)
        return 1
    except (httpx.HTTPError, ValidationError) as exc:
        print(f"[smoke] FAIL — unexpected error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(
        "[smoke] PASS — /health/ready, /version, /investigate, and the async "
        "/investigations + /decision path (inc-004) all satisfy the deployment gate",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
