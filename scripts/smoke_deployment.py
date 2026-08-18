"""Post-deploy smoke test: drive a real investigation against a live deployment.

Not a liveness probe. It runs the one thing the deployment exists to do, end to end, and reads
every response through the same models the application serves, so a schema drift between this
script and the API fails loudly rather than passing on a shape nobody checked.

What it proves: the revision is healthy and was built from this code; one investigation streams its
identity, then activity as it happens, then exactly one terminal event; and that terminal event is
a delivered brief rather than a failure category. The brief is checked for what a brief must always
have, and deliberately not for what it concluded: which cause an investigation reaches is the
model's to decide, and a smoke test that asserted a conclusion would be asserting the answer key.

Usage: uv run python scripts/smoke_deployment.py <base-url>
       (or set OPSPILOT_BASE_URL instead of the positional argument)
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

import httpx
from pydantic import ValidationError

from opspilot.api import ReadinessResponse, VersionResponse
from opspilot.config import RETRIEVAL_BACKEND

# inc-005: an authored incident whose window holds no deployment at all, so a healthy run has to
# admit an authoritative absence as well as ordinary evidence.
SMOKE_INCIDENT_ID = "inc-005"

REQUEST_TIMEOUT_S = 10.0
# One investigation is several model calls on a reasoning deployment, each slow. A short timeout
# reads as a hang when it is really the client giving up mid-run.
INVESTIGATION_TIMEOUT_S = 300.0
MAX_POLL_INTERVAL_S = 20.0


class SmokeTestFailure(RuntimeError):
    """Raised when a deployed instance fails the smoke-test contract."""


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
                f"[smoke] readiness attempt {attempt}: request failed ({last_error}), retrying",
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
    print(
        f"[smoke] version: application={version.application} version={version.version} "
        f"environment={version.environment}",
        flush=True,
    )
    _require(
        version.retrieval_backend == RETRIEVAL_BACKEND,
        f"/version reports backend {version.retrieval_backend!r}, expected "
        f"{RETRIEVAL_BACKEND!r}; the deployed revision was built from different code",
    )
    return version


def run_investigation(client: httpx.Client) -> None:
    """Stream one investigation and hold the deployment to the envelope a client depends on."""
    events: list[dict[str, Any]] = []
    with client.stream(
        "POST",
        "/investigations",
        json={"incident_id": SMOKE_INCIDENT_ID},
        timeout=INVESTIGATION_TIMEOUT_S,
    ) as resp:
        _require(
            resp.status_code == 200,
            f"POST /investigations returned HTTP {resp.status_code}",
        )
        for line in resp.iter_lines():
            if line.strip():
                events.append(json.loads(line))

    _require(bool(events), "the investigation stream carried no events at all")
    _require(
        events[0].get("event_type") == "identity" and bool(events[0].get("investigation_id")),
        f"the stream did not open with an identity: {events[0]}",
    )
    investigation_id = events[0]["investigation_id"]

    terminals = [e for e in events if e.get("event_type") == "terminal"]
    _require(
        len(terminals) == 1,
        f"expected exactly one terminal event, got {len(terminals)}",
    )
    _require(
        events[-1].get("event_type") == "terminal",
        "the terminal event was not the last thing on the stream",
    )

    activity = [e for e in events if e.get("event_type") == "activity"]
    _require(bool(activity), "the investigation reported no activity at all")
    _require(
        [e["sequence"] for e in activity] == list(range(1, len(activity) + 1)),
        "the activity sequence was not unbroken",
    )

    terminal = terminals[0]
    _require(
        terminal.get("failure") is None,
        f"the investigation ended in a failed execution: {terminal.get('failure')}",
    )
    brief = terminal.get("brief")
    _require(brief is not None, "the terminal event carried no brief")
    assert brief is not None  # narrowed by the check above
    _require(
        brief.get("outcome") in {"complete", "partial", "inconclusive"},
        f"the brief reported no recognizable outcome: {brief.get('outcome')}",
    )
    _require(bool(brief.get("text", "").strip()), "the brief was empty")
    # A probability would mean the deployment is presenting confidence as evidence.
    _require("%" not in brief["text"], "the brief presented a percentage")

    print(
        f"[smoke] investigation: id={investigation_id} incident={SMOKE_INCIDENT_ID} "
        f"outcome={brief['outcome']} activity_events={len(activity)}",
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
            for check in ("operational_records", "repository", "logs", "retrieval"):
                _require(
                    ready.checks.get(check) == "ok",
                    f"{check} check not ok: {ready.checks}",
                )
            check_version(client)
            run_investigation(client)
    except SmokeTestFailure as exc:
        print(f"[smoke] FAIL - {exc}", file=sys.stderr)
        return 1
    except (httpx.HTTPError, ValidationError) as exc:
        print(f"[smoke] FAIL - unexpected error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(
        "[smoke] PASS - the revision is healthy, was built from this code, and delivered one "
        f"grounded brief for {SMOKE_INCIDENT_ID}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
