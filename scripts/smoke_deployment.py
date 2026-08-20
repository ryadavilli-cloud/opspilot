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
# One model call rather than a whole run, but against a cold-started container and a reasoning
# deployment, so not the ordinary request timeout either.
QUESTION_TIMEOUT_S = 120.0
MAX_POLL_INTERVAL_S = 20.0


class SmokeTestFailure(RuntimeError):
    """Raised when a deployed instance fails the smoke-test contract."""


def _publish(investigation_id: str) -> None:
    """Hand the identifier to whatever runs after this, which is how the telemetry check knows
    which run to look for. Silent outside a workflow, where there is nothing to hand it to."""
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        return
    with open(output, "a", encoding="utf-8") as handle:
        handle.write(f"investigation_id={investigation_id}\n")


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
    # A deployed revision calling itself local means the template stopped telling it otherwise. The
    # value decides nothing at runtime, which is exactly why nothing else would ever notice.
    _require(
        version.environment != "local",
        f"/version reports environment={version.environment!r}: a deployed revision is reporting "
        "itself as a local one, so OPSPILOT_ENV is not reaching the container",
    )
    return version


def run_investigation(client: httpx.Client) -> str:
    """Stream one investigation and hold the deployment to the envelope a client depends on.

    Returns its identifier, because everything after this asks the deployment about the run it
    just did rather than about one prepared for the occasion."""
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
    return str(investigation_id)


def read_back_the_record(client: httpx.Client, investigation_id: str) -> dict[str, Any]:
    """The record outlives the request that made it, and carries what its citations rest on.

    A brief whose references resolve only while the process that wrote them is alive is not a
    record. This reads the investigation back through the same store any other reader would use,
    and checks that every reference the brief carries is one the record itself holds.
    """
    resp = client.get(f"/investigations/{investigation_id}")
    _require(
        resp.status_code == 200,
        f"reading back {investigation_id} returned HTTP {resp.status_code}: {resp.text[:300]}",
    )
    saved: dict[str, Any] = resp.json()

    _require(saved.get("investigation_id") == investigation_id, "the record read back another run")
    _require(bool(saved.get("brief")), "the record carries no brief")
    _require(bool(saved.get("operations")), "the record accounts for nothing it attempted")

    observed = {str(o.get("evidence_ref")) for o in saved.get("observations") or []}
    retrieved = {str(p.get("reference")) for p in saved.get("passages") or []}
    holds = observed | retrieved
    _require(bool(holds), "the record holds no reference, so the check below would be vacuous")

    cited = _cited_references(saved.get("assessment") or {})
    missing = sorted(ref for ref in cited if ref not in holds)
    _require(
        not missing,
        f"the record cites what it does not carry: {missing[:5]}; a reader holding this record "
        "could not check those citations",
    )

    print(
        f"[smoke] record: read back with {len(holds)} reference(s) it carries, "
        f"{len(cited)} cited and all resolving",
        flush=True,
    )
    return saved


def _cited_references(assessment: dict[str, Any]) -> set[str]:
    """Every reference the assessment states, from the fields that hold them.

    Read from fields rather than from prose: the assessment carries its references in lists for
    exactly this reason, and tokenizing the brief would invent a second grammar here.
    """
    cited: set[str] = set(assessment.get("what_happened_refs") or [])
    cited |= set(assessment.get("history_refs") or [])
    cited |= set(assessment.get("knowledge_used") or [])
    for candidate in assessment.get("candidates") or []:
        cited |= set(candidate.get("supporting") or [])
        cited |= set(candidate.get("weakening") or [])
    for action in assessment.get("actions") or []:
        if action.get("knowledge_ref"):
            cited.add(str(action["knowledge_ref"]))
    return {ref for ref in cited if ref}


def ask_about_the_record(client: httpx.Client, investigation_id: str) -> None:
    """One question about the finished investigation, answered from that record alone.

    What is proved here is that the route answers and that code checked what came back, not that
    the answer is good: an answer whose citation named nothing the record holds is replaced, and a
    replacement is still a valid response. Both outcomes are reported, and only a route that fails
    to answer at all is a failure.
    """
    resp = client.post(
        f"/investigations/{investigation_id}/questions",
        json={"question": "What evidence supports the leading candidate?"},
        timeout=QUESTION_TIMEOUT_S,
    )
    _require(
        resp.status_code == 200,
        f"asking about {investigation_id} returned HTTP {resp.status_code}: {resp.text[:300]}",
    )
    answer = resp.json()

    _require(answer.get("investigation_id") == investigation_id, "the answer names another run")
    _require(bool(str(answer.get("answer", "")).strip()), "the answer was empty")

    print(
        f"[smoke] question: answered with {len(answer.get('references') or [])} reference(s)"
        f"{' (refused and replaced by code)' if answer.get('refused') else ''}",
        flush=True,
    )


def an_unknown_investigation_is_a_clean_absence(client: httpx.Client) -> None:
    """Both routes over a completed record answer for an identifier that names nothing, rather
    than failing in a way that reads as the store being broken."""
    unknown = "smoke-no-such-investigation"
    read = client.get(f"/investigations/{unknown}")
    _require(read.status_code == 404, f"reading an unknown record returned HTTP {read.status_code}")

    asked = client.post(f"/investigations/{unknown}/questions", json={"question": "what happened?"})
    _require(
        asked.status_code == 404,
        f"asking about an unknown record returned HTTP {asked.status_code}",
    )
    print("[smoke] absence: an unknown identifier is refused cleanly on both routes", flush=True)


def an_unauthenticated_caller_is_refused(base_url: str) -> None:
    """The gate itself, asked without a token.

    Its own client, because the one the rest of this uses carries the token. What counts as refused
    is either an outright 401 or a redirect to sign in: the platform is configured to send a browser
    to a login page, and a redirect away from the application is a refusal to serve it.

    The health paths are deliberately not checked here. They are excluded from authentication so the
    platform's own probes can reach them, so they answer to anyone, and asserting otherwise would be
    asserting the opposite of how this is configured.
    """
    with httpx.Client(base_url=base_url, timeout=REQUEST_TIMEOUT_S, follow_redirects=False) as anon:
        resp = anon.post("/investigations", json={"incident_id": SMOKE_INCIDENT_ID})

    refused = resp.status_code in (401, 403) or (
        resp.status_code in (302, 303, 307) and "login" in resp.headers.get("location", "").lower()
    )
    _require(
        refused,
        f"an unauthenticated caller reached the investigation route: HTTP {resp.status_code}. "
        "The application starts real work and spends real model calls, so an open route is the "
        "one thing built-in authentication exists to prevent",
    )
    print(f"[smoke] unauthenticated: refused with HTTP {resp.status_code}", flush=True)


def _bearer_token(audience: str) -> str:
    """A token for the API, from whatever identity is already signed in.

    Shelling out to `az` rather than holding a credential: the workflow has already authenticated
    as its own principal, and this asks that session for a token rather than introducing a second
    way to prove who is calling.
    """
    import subprocess

    result = subprocess.run(
        [
            "az",
            "account",
            "get-access-token",
            "--resource",
            audience,
            "--query",
            "accessToken",
            "-o",
            "tsv",
        ],
        capture_output=True,
        text=True,
        shell=sys.platform == "win32",
    )
    _require(
        result.returncode == 0 and result.stdout.strip() != "",
        "could not obtain a token for the application. The deploy principal needs the app role "
        f"that permits it, and the audience {audience} must be the registration's identifier URI. "
        f"az said: {result.stderr.strip()[:300]}",
    )
    return result.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    base_url = argv[0] if argv else os.environ.get("OPSPILOT_BASE_URL")
    if not base_url:
        print("usage: smoke_deployment.py <base-url>  (or set OPSPILOT_BASE_URL)", file=sys.stderr)
        return 2

    ready_timeout_s = float(os.environ.get("OPSPILOT_SMOKE_READY_TIMEOUT_S", "300"))
    poll_interval_s = float(os.environ.get("OPSPILOT_SMOKE_POLL_INTERVAL_S", "5"))

    base_url = base_url.rstrip("/")
    audience = os.environ.get("OPSPILOT_AUTH_AUDIENCE", "")

    print(f"[smoke] target: {base_url}", flush=True)
    try:
        # Asked before anything else, and before a token exists: whether the route is open is a
        # property of the deployment rather than of this run, and a check that ran later could be
        # answered by a session the earlier checks had established.
        headers = {}
        if audience:
            an_unauthenticated_caller_is_refused(base_url)
            headers["Authorization"] = f"Bearer {_bearer_token(audience)}"
            print("[smoke] authenticated: holding a token for the application", flush=True)

        with httpx.Client(base_url=base_url, timeout=REQUEST_TIMEOUT_S, headers=headers) as client:
            ready = wait_for_ready(
                client, timeout_s=ready_timeout_s, poll_interval_s=poll_interval_s
            )
            for check in ("operational_records", "retrieval"):
                _require(
                    ready.checks.get(check) == "ok",
                    f"{check} check not ok: {ready.checks}",
                )
            check_version(client)
            investigation_id = run_investigation(client)
            read_back_the_record(client, investigation_id)
            ask_about_the_record(client, investigation_id)
            an_unknown_investigation_is_a_clean_absence(client)
            _publish(investigation_id)
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
