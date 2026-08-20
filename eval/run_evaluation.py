"""Run the offline evaluation over a scenario set and write one report.

Obtain or replay, per scenario. A scenario with a committed recording is replayed, which is what
keeps a deterministic run deterministic. The benign fixture has no recording and is invoked
directly, because it is evaluation corpus rather than an incident anyone can select. A scenario
with neither is reported as not run, with the reason named: coverage that varies between runs makes
two reports look alike when they are not, so the report says which mode each scenario ran in.

Advisory. This gates nothing, and its output is a document rather than an exit code.

Run. The full set needs the `llm` group because the fixture is obtained live; the fast scenario
replays and needs none of it:
  uv run --group dev python eval/run_evaluation.py
  uv run --group dev --group llm python eval/run_evaluation.py --full
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tests"))
sys.path.insert(0, str(REPO_ROOT / "eval"))

from answer_key import FIXTURE, SCENARIOS  # noqa: E402
from evaluation import Provenance, ScenarioResult, Source, evaluate  # noqa: E402
from fake_knowledge import knowledge_retriever  # noqa: E402
from fake_operational_records import corpus_documents, corpus_records  # noqa: E402

from opspilot import config  # noqa: E402
from opspilot.api import initial_state  # noqa: E402
from opspilot.investigation.graph import MODEL, RECORD, SERVICE, build_graph  # noqa: E402
from opspilot.llm.cassette import ReplayChatModel  # noqa: E402
from opspilot.llm.client import build_chat_model  # noqa: E402
from opspilot.record.completed import CompletedInvestigation  # noqa: E402
from opspilot.record.memory import InMemoryCompletedInvestigations  # noqa: E402
from opspilot.tools.contracts import IncidentRecord  # noqa: E402
from opspilot.tools.service import ToolService  # noqa: E402

# The cheapest useful advisory check: one straightforward single-cause scenario, run on a
# meaningful change. The full set is what a milestone is measured with.
FAST_SCENARIO = "inc-005"
REPORTS = REPO_ROOT / "eval" / "reports"


def _scenario_incident(scenario_id: str) -> IncidentRecord:
    return IncidentRecord(**corpus_records().incident(scenario_id, deadline_s=10))


def _fixture_incident() -> IncidentRecord:
    """The context the benign fixture is reported under, built from the row it names.

    There is no incident row for it, because nothing about it was ever paged. The reported symptom,
    the service, and the time are read from the log event itself so the only place that data lives
    is the generated corpus; the rest is what a report of something this small would carry. The
    window stays on that one event deliberately: the four rows of this class span five days and
    four services, and a window wide enough to hold all of them would also hold a real incident,
    which would make settling no cause the wrong answer rather than the right one.
    """
    row = next(
        document
        for document in corpus_documents()
        if document.get("kind") == "log" and document.get("event_id") == FIXTURE["reported_from"]
    )
    return IncidentRecord(
        number="INC0000000",
        incident_id=FIXTURE["id"],
        short_description=f"{row['service']}: {row['message']}",
        category="datastore",
        priority="3 - Moderate",
        impact="2 - Medium",
        urgency="2 - Medium",
        opened_at=row["ts"],
        state="In Progress",
        made_sla=True,
        reassignment_count=0,
        is_known_error=False,
    )


def _run_investigation(incident: IncidentRecord, model: Any) -> CompletedInvestigation | None:
    """One investigation through the real graph, and the record it wrote."""
    records = corpus_records()
    store = InMemoryCompletedInvestigations()
    service = ToolService(records, retriever_factory=knowledge_retriever)

    # Driven to completion for the record it writes; the streamed states are the runtime's own
    # business and the evaluation reads the persisted investigation rather than the run.
    for _ in build_graph().stream(
        initial_state("eval-1", incident),
        config={
            "configurable": {MODEL: model, SERVICE: service, RECORD: store},
            "recursion_limit": 2 * (config.CAPABILITY_CALL_CAP + config.MODEL_CALL_CAP) + 10,
        },
        stream_mode="values",
    ):
        pass
    return store.get("eval-1")


def obtain(scenario_id: str, source: Source) -> CompletedInvestigation | None:
    """The investigation this scenario is evaluated on, or nothing when it did not run."""
    if source.provenance is Provenance.NOT_RUN:
        return None
    return _run_investigation(
        _scenario_incident(scenario_id), ReplayChatModel(REPO_ROOT / source.detail)
    )


def obtain_fixture(source: Source) -> tuple[CompletedInvestigation | None, Source]:
    """The benign fixture, run live, with the source corrected to what actually happened.

    A live call is the one part of a run that can fail for reasons outside the repository: no
    credential, no network, a throttled deployment. That is reported as not run with the reason
    named, rather than being allowed to take down a report whose other results are already good.
    Only this path is forgiven. A replay that fails is a defect in the recording or the code and
    is left to raise, because nothing outside the repository can explain it.
    """
    if source.provenance is Provenance.NOT_RUN:
        return None, source
    try:
        return _run_investigation(_fixture_incident(), build_chat_model("azure")), source
    except Exception as error:  # noqa: BLE001 - reported, never swallowed
        return None, Source(
            Provenance.NOT_RUN, f"the live run of the benign fixture did not complete: {error}"
        )


def configuration_identity() -> dict[str, str]:
    """What this run ran under. Two reports are only comparable where these agree."""
    return {
        "model_deployment": config.AZURE_OPENAI_DEPLOYMENT or "(unset)",
        "reasoning_effort": config.REASONING_EFFORT,
        "capability_call_cap": str(config.CAPABILITY_CALL_CAP),
        "model_call_cap": str(config.MODEL_CALL_CAP),
        "investigation_deadline_s": str(config.INVESTIGATION_DEADLINE_SECONDS),
    }


def render(results: list[ScenarioResult], identity: dict[str, str], taken_at: str) -> str:
    """One document per run: per-scenario results with named failures, and no total."""
    lines = [
        "# OpsPilot evaluation report",
        "",
        f"Run at {taken_at}.",
        "",
        "## Configuration identity",
        "",
        *(f"- **{key}**: {value}" for key, value in identity.items()),
        "",
        "## Scenarios",
        "",
    ]
    for result in results:
        lines.append(f"### {result.scenario_id} - {result.source.provenance.value}")
        lines.append("")
        lines.append(f"Source: {result.source.detail}")
        lines.append("")
        if not result.ran:
            lines.extend(["Not run.", ""])
            continue
        if result.failures:
            lines.append("Failed:")
            lines.extend(f"- {failure}" for failure in result.failures)
        else:
            lines.append("No deterministic check failed.")
        lines.append("")
        if result.notes:
            lines.extend([f"_{note}_" for note in result.notes])
            lines.append("")
    ran = [r for r in results if r.ran]
    lines.extend(
        [
            "## Coverage",
            "",
            f"- {len(ran)} of {len(results)} scenario(s) ran.",
            f"- {len([r for r in ran if r.passed])} of those had no deterministic failure.",
            "",
            "No composite score is reported, and none of this gates a merge.",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="every scenario, not just the fast one")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    chosen = SCENARIOS if args.full else [s for s in SCENARIOS if s["id"] == FAST_SCENARIO]
    results: list[ScenarioResult] = []
    for scenario in chosen:
        scenario_id = scenario["id"]
        source = Source.for_scenario(scenario_id)
        record = obtain(scenario_id, source)
        results.append(evaluate(scenario_id, record, scenario["evaluation"], source))

    if args.full:
        record, source = obtain_fixture(Source.for_fixture(config.AZURE_OPENAI_DEPLOYMENT))
        results.append(
            evaluate(
                FIXTURE["id"],
                record,
                FIXTURE["evaluation"],
                source,
                benign=FIXTURE["evaluation"]["requires_no_immediate_action"],
            )
        )

    taken_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / f"{taken_at.replace(':', '')}.md"
    path.write_text(render(results, configuration_identity(), taken_at), encoding="utf-8")
    print(f"wrote {path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
