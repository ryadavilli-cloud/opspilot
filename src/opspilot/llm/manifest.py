"""The cassette replay manifest: every behaviour-affecting input other than the messages.

A recorded response is a function of far more than the messages, so a change to anything outside
them shifts real behaviour while the request key stays identical: CI then replays a response the
current inputs would never produce and passes green on a lie.

This is not hypothetical. Changing `reasoning_effort` from `low` to `medium`, because the model was
not working through all the evidence at `low`, left every cassette key unchanged, so the committed
results kept certifying responses recorded under the old setting.

What the manifest covers, and what it deliberately does not:

- **Prompt text** is substituted into the messages, so a prompt edit already changes the key. The
  resolved prompt *versions* are still recorded, because the registry is append-only: adding
  `diagnose_synthesize.v2` silently re-points `get_prompt` at new text, and pinning the versions
  turns that into a loud, named drift report. Only the prompts a recording actually pinned are
  compared: the registry is global, so registering a prompt for one workflow must not invalidate
  cassettes recorded for another that never resolved it.
- **Provider identity is excluded on purpose.** Replay runs under the `replay` provider while the
  recording ran against Azure, so comparing it would fail every time and teach everyone to ignore
  the check. The knobs that shape output are compared instead.
- **`max_tokens`, stop sequences, and safety settings** are not sent by this codebase. They join
  the manifest with the request that starts sending them, not before: a field pinned to a constant
  nobody sets is coverage theatre.
"""

from __future__ import annotations

import hashlib
import json

from opspilot import config
from opspilot.llm.prompts import resolved_versions


def behaviour_manifest(*, deployment: str) -> dict[str, str]:
    """The behaviour-affecting configuration a recorded response depends on.

    `deployment` is passed in rather than read from config so replay can rebuild the manifest
    around the deployment the cassette was actually recorded against, while every other field
    reflects what the current code would send.
    """
    return {
        "deployment": deployment,
        "reasoning_effort": config.REASONING_EFFORT,
        "azure_api_version": config.AZURE_OPENAI_API_VERSION,
        "prompt_versions": ",".join(f"{n}={v}" for n, v in sorted(resolved_versions().items())),
    }


def manifest_digest(manifest: dict[str, str]) -> str:
    """Stable hash of a manifest, used as the per-request key's prefix component.

    Hashes the manifest whole. Replay keys off the manifest the cassette recorded, not the current
    one, so narrowing this would only invalidate every key already written.
    """
    blob = json.dumps(manifest, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _prompt_map(value: str) -> dict[str, str]:
    pairs = (part.split("=", 1) for part in value.split(",") if "=" in part)
    return {name: version for name, version in pairs}


def _prompt_drift(recorded: str, current: str) -> list[str]:
    """Drift only among the prompts the recording actually pinned.

    A prompt registered after the recording is not drift: the recorded run never resolved it, so it
    cannot have shaped the response. A prompt the recording pinned that has since moved or vanished
    is drift, because that one did.
    """
    was, now = _prompt_map(recorded), _prompt_map(current)
    return [
        f"prompt {name}: recorded {version!r}, current {now.get(name, '(absent)')!r}"
        for name, version in sorted(was.items())
        if now.get(name) != version
    ]


def manifest_drift(recorded: dict[str, str], current: dict[str, str]) -> list[str]:
    """Human-readable description of every field that differs, so a stale cassette says WHICH
    input moved rather than only that a lookup missed. Empty when the two agree."""
    drift = []
    for key in sorted(set(recorded) | set(current)):
        was, now = recorded.get(key, "(absent)"), current.get(key, "(absent)")
        if key == "prompt_versions":
            drift.extend(_prompt_drift(was, now))
        elif was != now:
            drift.append(f"{key}: recorded {was!r}, current {now!r}")
    return drift
