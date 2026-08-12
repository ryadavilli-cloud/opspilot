"""Record/replay for `ChatModel` — how LLM-driven tests gate CI deterministically.

CI cannot reach Ollama or Azure Foundry, and model output is non-deterministic, so the LLM wiring
tests replay a committed *cassette*: a JSON file of (request -> response) interactions recorded once
against a live model. `ReplayChatModel` looks up each request by a stable content hash and returns
the recorded `ChatResult`; a request with no recorded match fails loudly (re-record the cassette).
`RecordingChatModel` wraps a live model to capture a cassette locally.

Cassettes store the request messages verbatim so a reviewer can read what the model was asked; the
hash keys the lookup so replay is order-independent.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from opspilot.llm.base import ChatMessage, ChatModel, ChatResult
from opspilot.llm.manifest import behaviour_manifest, manifest_digest, manifest_drift


class CassetteDriftError(RuntimeError):
    """A cassette was recorded under a different behaviour manifest than the code now uses.

    Raised at load time, naming the drifted fields, rather than letting the run proceed to a
    per-request miss (or worse, a hit that replays a response the current inputs would never
    produce). See `llm/manifest.py` for what the manifest covers and why.
    """


def request_key(manifest: dict[str, str], messages: list[ChatMessage], temperature: float) -> str:
    """Stable content hash of a request — the replay lookup key. Canonical JSON so it is
    reproducible across processes and machines.

    The manifest is part of the key, not just a load-time check, so two cassettes recorded under
    different settings can never collide even if someone merges them by hand.
    """
    payload = {
        "manifest": manifest_digest(manifest),
        "temperature": round(temperature, 6),
        "messages": [{"role": m.role, "content": m.content} for m in messages],
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _result_to_dict(r: ChatResult) -> dict:
    return {
        "text": r.text,
        "model_id": r.model_id,
        "prompt_version": r.prompt_version,
        "finish_reason": r.finish_reason,
        "usage": r.usage,
    }


def _result_from_dict(d: dict) -> ChatResult:
    return ChatResult(
        text=d["text"],
        model_id=d.get("model_id", ""),
        prompt_version=d.get("prompt_version", ""),
        finish_reason=d.get("finish_reason", ""),
        usage=d.get("usage", {}),
    )


class ReplayChatModel:
    """Serves recorded responses from a cassette. Unknown request -> KeyError (re-record).

    Load fails closed on manifest drift: a cassette recorded under a different `reasoning_effort`,
    API version, or prompt version is stale by definition, and replaying it would certify
    behaviour the current code cannot produce.
    """

    def __init__(self, cassette_path: str | Path) -> None:
        self._path = Path(cassette_path)
        data = json.loads(self._path.read_text(encoding="utf-8"))
        self.model_id = data.get("model_id", "replay")

        recorded = data.get("manifest")
        if recorded is None:
            raise CassetteDriftError(
                f"{self._path.name} predates the replay manifest and cannot be validated; "
                "re-record it against a live model"
            )
        # Rebuild around the RECORDED model so the comparison isolates the settings that drifted,
        # not the model itself, which replay never resolves live.
        drift = manifest_drift(recorded, behaviour_manifest(model_id=self.model_id))
        if drift:
            raise CassetteDriftError(
                f"{self._path.name} was recorded under different behaviour-affecting settings; "
                f"re-record it. Drift: " + "; ".join(drift)
            )
        self._manifest = recorded
        self._by_key = {i["key"]: i["response"] for i in data.get("interactions", [])}

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.0,
    ) -> ChatResult:
        key = request_key(self._manifest, messages, temperature)
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
        self.model_id = inner.model_id
        self._path = Path(cassette_path)
        self._interactions: list[dict] = []
        # Captured once at construction: the manifest describes the run that produced the
        # responses, so it must not be re-read per call and drift mid-recording.
        self._manifest = behaviour_manifest(model_id=self.model_id)

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.0,
    ) -> ChatResult:
        result = self._inner.complete(messages, temperature=temperature)
        self._interactions.append(
            {
                "key": request_key(self._manifest, messages, temperature),
                "request": {
                    "temperature": temperature,
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
                    "model_id": self.model_id,
                    "manifest": self._manifest,
                    "interactions": self._interactions,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
