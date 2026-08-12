"""Record the turn's synthesis call into a replay cassette, so CI never calls a model.

Drives the real streaming endpoint rather than rebuilding the prompt by hand. Replay looks the
request up by a content hash of the messages, so anything that assembles them differently here
would record a cassette the replay test could never hit.

Only the model is live. The operational records come from the authored corpus fake, so this
touches no deployed container and no Azure resource.

The cassette is invalidated by any change to the synthesis prompt, the evidence digest, or the
evidence plan, because each of those moves the messages. That is loud rather than silent: replay
raises with the cassette named. Re-record after such a change, not before.

Run (spends against the configured API key):
  uv run python eval/record_turn_synthesis.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# The corpus fake lives beside the tests that use it, and driving the same source is what keeps the
# recorded messages identical to the ones replay will look up.
sys.path.insert(0, str(REPO_ROOT / "tests"))

from fake_operational_records import corpus_records  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from opspilot.api import (  # noqa: E402
    app,
    get_operational_records,
    get_service,
    get_synthesis_model,
)
from opspilot.llm.cassette import RecordingChatModel  # noqa: E402
from opspilot.llm.client import build_chat_model  # noqa: E402
from opspilot.tools.service import ToolService  # noqa: E402

# inc-005: a Redis eviction storm. Its authored answer key records no deployment anywhere in the
# window, so the run exercises an authoritative absence as well as ordinary admitted evidence.
INCIDENT = "inc-005"
# The model the deployment runs (`infra/main.bicep`), so the recorded response is representative of
# what the hosted app produces. A reasoning model: the client sends `reasoning_effort` and omits
# temperature and seed, and the manifest pins that effort so a change to it invalidates the
# cassette rather than silently replaying a response recorded under a different setting.
RECORD_MODEL = "gpt-5-mini"
CASSETTE = REPO_ROOT / "eval" / "cassettes" / "turn_synthesis.json"


def main() -> None:
    CASSETTE.parent.mkdir(parents=True, exist_ok=True)
    # The provider is named rather than config-resolved: the local default is Ollama, and a
    # cassette recorded against it would certify a model the deployment does not run.
    model = RecordingChatModel(build_chat_model("openai", model=RECORD_MODEL), CASSETTE)
    records = corpus_records()

    app.dependency_overrides[get_operational_records] = lambda: records
    app.dependency_overrides[get_service] = lambda: ToolService(records)
    app.dependency_overrides[get_synthesis_model] = lambda: model
    try:
        with (
            TestClient(app) as client,
            client.stream("POST", "/turns", json={"incident_id": INCIDENT}) as response,
        ):
            response.raise_for_status()
            events = [line for line in response.iter_lines() if line.strip()]
    finally:
        app.dependency_overrides.pop(get_operational_records, None)
        app.dependency_overrides.pop(get_service, None)
        app.dependency_overrides.pop(get_synthesis_model, None)

    print(f"incident:     {INCIDENT}")
    print(f"model:        {model.model_id}")
    print(f"stream events: {len(events)}")
    print(f"wrote {CASSETTE.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
