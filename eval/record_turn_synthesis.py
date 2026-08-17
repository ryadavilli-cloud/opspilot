"""Record the turn's synthesis call into a replay cassette, so CI never calls a model.

Drives the real streaming endpoint rather than rebuilding the prompt by hand. Replay looks the
request up by a content hash of the messages, so anything that assembles them differently here
would record a cassette the replay test could never hit.

Only the model is live, and it is reached the way the deployed application reaches it: through the
Azure adapter, against the chat deployment the application calls. That is the point of the
recording. A response taken through any other client would certify a serving path the application
never takes, and two endpoints answering to the same model name are still two endpoints. The
operational records come from the authored corpus fake, so nothing else here touches a deployed
resource.

The cassette is invalidated by any change to the synthesis prompt, the evidence digest, or the
evidence plan, because each of those moves the messages. That is loud rather than silent: replay
raises with the cassette named. Re-record after such a change, not before.

Run (spends one call against the Azure chat deployment; authenticates as the signed-in identity):
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

from opspilot import config  # noqa: E402
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
CASSETTE = REPO_ROOT / "eval" / "cassettes" / "turn_synthesis.json"


def main() -> None:
    # Refused rather than defaulted. Without these the adapter would fall back to the local
    # development model name, and the recording would certify a model and an endpoint the
    # application does not call while looking like a successful take.
    if not config.AZURE_OPENAI_ENDPOINT or not config.AZURE_OPENAI_DEPLOYMENT:
        raise SystemExit(
            "set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT to the chat deployment the "
            "application calls; a recording taken against anything else certifies a path it "
            "never takes"
        )

    CASSETTE.parent.mkdir(parents=True, exist_ok=True)
    # The provider is named rather than config-resolved, because the local default is Ollama. It is
    # named `azure` specifically: the deployed application reaches its model through this adapter,
    # so this is the one client whose responses are evidence about what the deployment produces.
    # Auth is keyless, as it is in the deployment; only the identity differs.
    model = RecordingChatModel(build_chat_model("azure"), CASSETTE)
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
