"""Record one whole investigation into a replay cassette, so CI never calls a model.

Every model call the run makes is captured: the objective, one selection call per gathering step,
the synthesis, and a correction where one was needed. Driving the real streaming request rather
than rebuilding prompts by hand is what keeps that honest, since replay looks each request up by a
content hash of its messages and anything assembling them differently here would record a cassette
the replay test could never hit.

Only the model is live, and it is reached the way the deployed application reaches it: through the
Azure adapter, against the chat deployment the application calls. That is the point of the
recording. A response taken through any other client would certify a serving path the application
never takes, and two endpoints answering to the same model name are still two endpoints. The
operational records and the knowledge the run searches both come from the authored corpus, so
nothing else here touches a deployed resource. Both are needed: a run recorded without a knowledge
backend captures the investigator reaching for retrieval and being told it is unavailable, which is
a recording of the wrong thing.

The cassette is invalidated by any change to the synthesis prompt, the evidence digest, or the
evidence plan, because each of those moves the messages. That is loud rather than silent: replay
raises with the cassette named. Re-record after such a change, not before.

Authentication is keyless: the adapter authenticates as the environment's identity, so a local
run needs `az login` and an identity holding the data-plane role on the account.

One cassette per recorded incident, named for it, because a cassette is evidence about one run
and two incidents produce two different sets of messages.

Run (spends one call per model call the run makes; the `llm` group carries the SDK the adapter
imports):
  uv run --group llm python eval/record_investigation.py inc-005
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# The corpus fake lives beside the tests that use it, and driving the same source is what keeps the
# recorded messages identical to the ones replay will look up.
sys.path.insert(0, str(REPO_ROOT / "tests"))

from fake_knowledge import knowledge_retriever  # noqa: E402
from fake_operational_records import corpus_records  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from opspilot import config  # noqa: E402
from opspilot.api import (  # noqa: E402
    app,
    get_model,
    get_operational_records,
    get_record,
    get_service,
)
from opspilot.llm.cassette import RecordingChatModel  # noqa: E402
from opspilot.llm.client import build_chat_model  # noqa: E402
from opspilot.record.memory import InMemoryCompletedInvestigations  # noqa: E402
from opspilot.tools.service import ToolService  # noqa: E402

# The incidents worth having a recording of, and why each one earns the model calls it costs.
#   inc-005: a Redis eviction storm. Its authored answer key records no deployment anywhere in the
#            window, so the run exercises an authoritative absence alongside ordinary evidence.
#   inc-004: the ambiguous one. Its first pass cannot close, which is what gives analysis something
#            real to send back for, so this is where the one return is observable on a real model.
#   inc-007: a recurrence of an incident that already has a write-up. Whether retrieved knowledge
#            changes what an investigation checks or concludes is answerable here and nowhere else
#            in the corpus, because this is the only incident whose answer is already written down.
RECORDABLE = ("inc-005", "inc-004", "inc-007")
DEFAULT_INCIDENT = "inc-005"


def cassette_for(incident: str) -> Path:
    return REPO_ROOT / "eval" / "cassettes" / f"{incident}.json"


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    incident = argv[0] if argv else DEFAULT_INCIDENT
    if incident not in RECORDABLE:
        raise SystemExit(
            f"{incident} is not one of the recorded incidents: {', '.join(RECORDABLE)}"
        )
    cassette = cassette_for(incident)
    # Refused rather than defaulted. Without these the adapter would fall back to the local
    # development model name, and the recording would certify a model and an endpoint the
    # application does not call while looking like a successful take.
    if not config.AZURE_OPENAI_ENDPOINT or not config.AZURE_OPENAI_DEPLOYMENT:
        raise SystemExit(
            "set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT to the chat deployment the "
            "application calls; a recording taken against anything else certifies a path it "
            "never takes"
        )

    cassette.parent.mkdir(parents=True, exist_ok=True)
    # The provider is named rather than config-resolved: the deployed application reaches its
    # model through this adapter, so this is the one client whose responses are evidence about
    # what the deployment produces. Auth is keyless, as it is in the deployment; only the identity
    # differs.
    model = RecordingChatModel(build_chat_model("azure"), cassette)
    records = corpus_records()

    app.dependency_overrides[get_operational_records] = lambda: records
    app.dependency_overrides[get_service] = lambda: ToolService(
        records, retriever_factory=knowledge_retriever
    )
    app.dependency_overrides[get_model] = lambda: model
    # The completed record is held in memory for the length of this run. A recording is
    # evidence about what the model produced, and writing one into the deployed store would
    # leave an investigation behind that no one asked for, on a store shared with real runs.
    app.dependency_overrides[get_record] = InMemoryCompletedInvestigations
    try:
        with (
            TestClient(app) as client,
            client.stream("POST", "/investigations", json={"incident_id": incident}) as response,
        ):
            response.raise_for_status()
            events = [line for line in response.iter_lines() if line.strip()]
    finally:
        app.dependency_overrides.pop(get_operational_records, None)
        app.dependency_overrides.pop(get_service, None)
        app.dependency_overrides.pop(get_model, None)
        app.dependency_overrides.pop(get_record, None)

    print(f"incident:     {incident}")
    print(f"deployment:   {model.deployment}")
    print(f"stream events: {len(events)}")
    print(f"model calls:  {len(model._interactions)}")
    print(f"wrote {cassette.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
