"""Record and replay for the chat seam: how model-driven tests gate CI deterministically.

CI cannot reach Azure OpenAI, and model output is not reproducible, so the tests that need a real
response replay a committed *cassette*: a JSON file of recorded interactions. `ReplayChatModel`
looks each request up by a stable content hash and returns the recorded result; a request with no
recorded match fails loudly rather than answering with something else. `RecordingChatModel` wraps
the live adapter to capture a cassette locally.

Cassettes store the request messages verbatim so a reviewer can read what the model was asked; the
hash keys the lookup so replay is order-independent.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from opspilot.llm.base import ChatMessage, ChatModel, ChatResult
from opspilot.llm.manifest import behaviour_manifest, manifest_digest, manifest_drift


class CassetteDriftError(RuntimeError):
    """A cassette was recorded under a different behaviour manifest than the code now uses.

    Raised at load time, naming the drifted fields, rather than letting the run proceed to a
    per-request miss or, worse, a hit that replays a response the current inputs would never
    produce.
    """


def request_key(manifest: dict[str, str], task: str, messages: list[ChatMessage]) -> str:
    """Stable content hash of a request, and the replay lookup key. Canonical JSON so it is
    reproducible across processes and machines.

    The manifest is part of the key, not only a load-time check, so two cassettes recorded under
    different settings can never collide even if someone merges them by hand.
    """
    payload = {
        "manifest": manifest_digest(manifest),
        "task": task,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _result_to_dict(r: ChatResult) -> dict[str, object]:
    return {
        "text": r.text,
        "task": r.task,
        "deployment": r.deployment,
        "prompt_version": r.prompt_version,
        "finish_reason": r.finish_reason,
        "latency_ms": r.latency_ms,
        "usage": r.usage,
    }


def _result_from_dict(d: dict[str, Any]) -> ChatResult:
    return ChatResult(
        text=d["text"],
        task=d.get("task", ""),
        deployment=d.get("deployment", ""),
        prompt_version=d.get("prompt_version", ""),
        finish_reason=d.get("finish_reason", ""),
        latency_ms=d.get("latency_ms", 0.0),
        usage=d.get("usage", {}),
    )


class ReplayChatModel:
    """Serves recorded responses from a cassette. An unknown request raises, so re-record.

    Load fails closed on manifest drift: a cassette recorded under a different reasoning effort,
    API version, or prompt version is stale by definition, and replaying it would certify behaviour
    the current code cannot produce.
    """

    def __init__(self, cassette_path: str | Path) -> None:
        self._path = Path(cassette_path)
        data = json.loads(self._path.read_text(encoding="utf-8"))
        self.deployment = data.get("deployment", "replay")

        recorded = data.get("manifest")
        if recorded is None:
            raise CassetteDriftError(
                f"{self._path.name} predates the replay manifest and cannot be validated; "
                "re-record it against a live model"
            )
        # Rebuilt around the RECORDED deployment so the comparison isolates the settings that
        # drifted, not the deployment itself, which replay never resolves live.
        drift = manifest_drift(recorded, behaviour_manifest(deployment=self.deployment))
        if drift:
            raise CassetteDriftError(
                f"{self._path.name} was recorded under different behaviour-affecting settings; "
                f"re-record it. Drift: " + "; ".join(drift)
            )
        self._manifest = recorded
        self._by_key = {i["key"]: i["response"] for i in data.get("interactions", [])}

    def complete(self, task: str, messages: list[ChatMessage]) -> ChatResult:
        key = request_key(self._manifest, task, messages)
        try:
            return _result_from_dict(self._by_key[key])
        except KeyError:
            raise KeyError(
                f"no recorded response for request {key[:12]}… in {self._path.name}; "
                "re-record the cassette against a live model"
            ) from None


class RecordingChatModel:
    """Wraps a live `ChatModel`, capturing every interaction to a cassette on disk (local use)."""

    def __init__(self, inner: ChatModel, cassette_path: str | Path) -> None:
        self._inner = inner
        self.deployment = inner.deployment
        self._path = Path(cassette_path)
        self._interactions: list[dict[str, object]] = []
        # Captured once at construction: the manifest describes the run that produced the
        # responses, so it must not be re-read per call and drift mid-recording.
        self._manifest = behaviour_manifest(deployment=self.deployment)

    def complete(self, task: str, messages: list[ChatMessage]) -> ChatResult:
        result = self._inner.complete(task, messages)
        self._interactions.append(
            {
                "key": request_key(self._manifest, task, messages),
                "request": {
                    "task": task,
                    "messages": [{"role": m.role, "content": m.content} for m in messages],
                },
                "response": _result_to_dict(result),
            }
        )
        self._flush()
        return result

    def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(
                {
                    "deployment": self.deployment,
                    "manifest": self._manifest,
                    "interactions": self._interactions,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
