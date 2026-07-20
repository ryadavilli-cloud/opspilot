"""Post-deploy smoke test — exercises the real OpsPilot investigation workflow against a live
deployment, not just process liveness. Deserializes every response into the same Pydantic
models the API uses, so a schema drift between this script and the API fails loudly.

Usage: uv run python scripts/smoke_deployment.py <base-url>
       (or set OPSPILOT_BASE_URL instead of the positional argument)
"""

from __future__ import annotations

import os
import sys
import time

import httpx
from pydantic import ValidationError

from opspilot.api import InvestigationResponse, ReadinessResponse, VersionResponse

# inc-004: a fixed, answer-keyed incident (data/answer_key/scenarios.yaml) — same fixture
# used by tests/test_api.py::test_investigation_smoke_path_over_bm25.
SMOKE_INCIDENT_ID = "inc-004"
SMOKE_INCIDENT_SUMMARY = "checkout-api returning 500s shortly after this morning's deployment."
REQUEST_TIMEOUT_S = 10.0
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


def run_investigation(client: httpx.Client) -> InvestigationResponse:
    resp = client.post(
        "/investigate",
        json={"incident_id": SMOKE_INCIDENT_ID, "summary": SMOKE_INCIDENT_SUMMARY},
    )
    _require(
        resp.status_code == 200,
        f"/investigate returned HTTP {resp.status_code}: {resp.text[:500]}",
    )
    investigation = InvestigationResponse.model_validate(resp.json())

    _require(
        investigation.status == "completed",
        f"investigation status={investigation.status!r}, expected 'completed'",
    )
    _require(investigation.report is not None, "investigation completed but report is None")
    report = investigation.report
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

    print(
        f"[smoke] investigation: incident_id={investigation.incident_id} "
        f"status={investigation.status} implementation={investigation.runtime.implementation} "
        f"provider={investigation.runtime.provider} model_id={investigation.runtime.model_id} "
        f"hypothesis={report.hypothesis!r} "
        f"evidence={len(report.evidence)} citations={len(report.citations)}",
        flush=True,
    )
    return investigation


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
            run_investigation(client)
    except SmokeTestFailure as exc:
        print(f"[smoke] FAIL — {exc}", file=sys.stderr)
        return 1
    except (httpx.HTTPError, ValidationError) as exc:
        print(f"[smoke] FAIL — unexpected error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(
        "[smoke] PASS — /health/ready, /version, and /investigate(inc-004) all satisfy "
        "the deployment gate",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
