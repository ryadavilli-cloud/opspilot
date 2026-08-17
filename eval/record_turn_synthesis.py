"""Record the turn's synthesis call into a replay cassette, so CI never calls a model.

Drives the real streaming endpoint rather than rebuilding the prompt by hand. Replay looks the
request up by a content hash of the messages, so anything that assembles them differently here
would record a cassette the replay test could never hit.

Only the model call is live, and it goes through the same Azure adapter the application ships
with, so the recorded response comes from the provider boundary the deployment actually uses. The
operational records come from the authored corpus fake, so this touches no deployed container and
no other Azure resource.

The cassette is invalidated by any change to the synthesis prompt, the evidence digest, or the
evidence plan, because each of those moves the messages. That is loud rather than silent: replay
raises with the cassette named. Re-record after such a change, not before.

Authentication is keyless: the adapter authenticates as the environment's identity, so a local run
needs `az login` and an identity holding the data-plane role on the account. `AZURE_OPENAI_ENDPOINT`
names the account.

Run (spends against the configured Azure OpenAI deployment):
  AZURE_OPENAI_ENDPOINT=https://<account>.openai.azure.com/ \
    uv run --group llm python eval/record_turn_synthesis.py
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
# The chat deployment the application calls (`infra/main.bicep`). A reasoning deployment: the
# client sends `reasoning_effort`, and the manifest pins that effort so a change to it invalidates
# the cassette rather than silently replaying a response recorded under a different setting.
RECORD_DEPLOYMENT = "gpt-5-mini"
CASSETTE = REPO_ROOT / "eval" / "cassettes" / "turn_synthesis.json"


def main() -> None:
    CASSETTE.parent.mkdir(parents=True, exist_ok=True)
    # The provider and deployment are named rather than config-resolved, so a local environment
    # pointed somewhere else cannot quietly record a cassette against it.
    model = RecordingChatModel(build_chat_model("azure", deployment=RECORD_DEPLOYMENT), CASSETTE)
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
    print(f"deployment:   {model.deployment}")
    print(f"stream events: {len(events)}")
    print(f"wrote {CASSETTE.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
