"""Run the offline evaluation over a scenario set and write one report.

Obtain or replay, per scenario. A scenario with a committed recording is replayed, which is what
keeps a deterministic run deterministic. The benign fixture has no recording and is invoked
directly, because it is evaluation corpus rather than an incident anyone can select. A scenario
with neither is reported as not run, with the reason named: coverage that varies between runs makes
two reports look alike when they are not, so the report says which mode each scenario ran in.

Advisory. This gates nothing, and its output is a document rather than an exit code.

Run. Both lanes need the `llm` group, because the judge is a live call in either; the full set
additionally obtains the benign fixture live. Without it the investigations still replay and the
report says the judge did not run:
  uv run --group dev --group llm python eval/run_evaluation.py
  uv run --group dev --group llm python eval/run_evaluation.py --full

Keeping. A run worth keeping is also written to the evaluation store, where the application lists
and reads it; keeping is opt-in so an exploratory run does not enter the history. The identity
running this must hold write on that container, which the application's own identity does not:
  uv run --group dev --group llm python eval/run_evaluation.py --full --keep "before prompt v6"
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
from comparisons import (  # noqa: E402
    ComparisonResult,
    adaptive_value,
    retrieval_influence,  # noqa: E402
)
from comparisons import not_evaluable as _not_evaluable  # noqa: E402
from evaluation import Provenance, ScenarioResult, Source, evaluate  # noqa: E402
from fake_knowledge import knowledge_retriever  # noqa: E402
from fake_operational_records import corpus_documents, corpus_records  # noqa: E402
from fixed_path import fixed_path  # noqa: E402
from judge import (  # noqa: E402
    DIAGNOSIS_MATCH,
    PROMPTS,
    QUALITIES,
    Judged,
    UnusableVerdict,
    judge,
)

from opspilot import config  # noqa: E402
from opspilot.api import initial_state  # noqa: E402
from opspilot.evaluation.judge_model import build_judge_model  # noqa: E402
from opspilot.evaluation.record import (  # noqa: E402
    ComparisonDifference,
    ComparisonRun,
    DeterministicCheck,
    EvaluationRun,
    JudgeVerdict,
    ScenarioRun,
)
from opspilot.investigation.graph import MODEL, RECORD, SERVICE, build_graph  # noqa: E402
from opspilot.investigation.harness import HARNESS, Harness  # noqa: E402
from opspilot.llm.cassette import ReplayChatModel  # noqa: E402
from opspilot.llm.claude import EFFORT as JUDGE_EFFORT  # noqa: E402
from opspilot.llm.claude import THINKING as JUDGE_THINKING  # noqa: E402
from opspilot.llm.client import build_chat_model  # noqa: E402
from opspilot.llm.prompts import get_prompt  # noqa: E402
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


def _run_investigation(
    incident: IncidentRecord, model: Any, harness: Harness | None = None, run_id: str = "eval-1"
) -> CompletedInvestigation | None:
    """One investigation through the real graph, and the record it wrote."""
    records = corpus_records()
    store = InMemoryCompletedInvestigations()
    service = ToolService(records, retriever_factory=knowledge_retriever)

    # Driven to completion for the record it writes; the streamed states are the runtime's own
    # business and the evaluation reads the persisted investigation rather than the run.
    for _ in build_graph().stream(
        initial_state(run_id, incident),
        config={
            "configurable": {MODEL: model, SERVICE: service, RECORD: store, HARNESS: harness},
            "recursion_limit": 2 * (config.CAPABILITY_CALL_CAP + config.MODEL_CALL_CAP) + 10,
        },
        stream_mode="values",
    ):
        pass
    return store.get(run_id)


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


def judged(
    record: CompletedInvestigation | None, scenario: dict[str, Any], reported: str
) -> Judged:
    """The judge over one completed investigation, or the reason there is no judgement.

    Each way there is none is said rather than left blank, and they are told apart: the scenario did
    not run, no deployment is configured, the deployment could not be reached, the call did not
    complete, or the answer was not a judgement. The last is refused rather than repaired, because
    a category nobody chose is worse than no category.
    """
    scenario_id = scenario.get("id", "")
    if record is None:
        return Judged(scenario_id, note="no investigation to judge")
    if not (config.AZURE_CLAUDE_ENDPOINT and config.AZURE_CLAUDE_DEPLOYMENT):
        return Judged(scenario_id, note="no judge model deployment is configured")
    try:
        model = build_judge_model()
    except Exception as error:  # noqa: BLE001 - reported, never swallowed
        return Judged(scenario_id, note=f"the judge could not be reached: {error}")
    try:
        return judge(model, record, scenario, reported)
    except UnusableVerdict as error:
        return Judged(scenario_id, note=f"the judge did not return a usable verdict: {error}")
    except Exception as error:  # noqa: BLE001 - reported, never swallowed
        return Judged(scenario_id, note=f"the judge call did not complete: {error}")


# Which scenario the adaptive comparison is tried on, in order. None is declared to satisfy it
# until a run shows the difference, so the first that does is the one it is reported on and the
# ones before it are reported as having shown none.
ADAPTIVE_CANDIDATES = ("inc-004", "inc-006", "inc-007")
RETRIEVAL_SCENARIO = "inc-007"

LIVE = "run live against the configured deployment"


class ConditionFailed(RuntimeError):
    """One condition of a comparison could not be obtained."""


def _live(incident: IncidentRecord, harness: Harness | None, run_id: str):
    """One condition, run live, or a refusal naming what stopped it.

    Both conditions are live calls, which is the one part of a comparison that can fail for reasons
    outside the repository: a throttled deployment, an expired credential, no network. That is
    reported as a comparison nobody could set up, rather than being allowed to end a report whose
    scenario results are already good.
    """
    try:
        record = _run_investigation(incident, build_chat_model("azure"), harness, run_id)
    except Exception as error:  # noqa: BLE001 - reported, never swallowed
        raise ConditionFailed(str(error)) from error
    if record is None:
        raise ConditionFailed("the condition completed without writing a record")
    return record


def compare_adaptive(scenario: dict[str, Any]) -> ComparisonResult:
    """The same scenario twice: as the investigator chooses, and over a fixed order.

    Both conditions run live. The design forbids one recorded response answering both arms, and
    running one arm from a recording and the other live would leave the two differing in how they
    were obtained as well as in the variable, which is a second difference nobody asked for.
    """
    scenario_id = scenario["id"]
    incident = _scenario_incident(scenario_id)
    try:
        adaptive = _live(incident, None, f"adaptive-{scenario_id}")
        fixed = _live(incident, Harness(next_action=fixed_path), f"fixed-{scenario_id}")
    except ConditionFailed as error:
        return _not_evaluable(
            "adaptive value", scenario_id, f"a condition did not complete: {error}"
        )

    reported = incident.short_description
    return adaptive_value(
        scenario,
        adaptive,
        fixed,
        Source(Provenance.OBTAINED, LIVE),
        Source(Provenance.OBTAINED, LIVE),
        judged(adaptive, scenario, reported),
        judged(fixed, scenario, reported),
    )


def compare_retrieval_influence(scenario: dict[str, Any]) -> ComparisonResult:
    """The same scenario twice, retrieval running in both, its passages reaching only one."""
    scenario_id = scenario["id"]
    incident = _scenario_incident(scenario_id)
    try:
        shown = _live(incident, None, f"shown-{scenario_id}")
        withheld = _live(incident, Harness(withhold_knowledge=True), f"withheld-{scenario_id}")
    except ConditionFailed as error:
        return _not_evaluable(
            "retrieval influence", scenario_id, f"a condition did not complete: {error}"
        )

    return retrieval_influence(
        scenario,
        shown,
        withheld,
        Source(Provenance.OBTAINED, LIVE),
        Source(Provenance.OBTAINED, LIVE),
    )


def run_comparisons(chosen: list[dict[str, Any]]) -> list[ComparisonResult]:
    """Both comparisons, where the chosen set includes their scenarios.

    The adaptive one walks its candidates and stops at the first that shows a difference, because
    it is a falsification test rather than a benchmark: one scenario where the adaptive path did
    better is the claim, and the candidates it passed over are reported as having shown none.
    """
    by_id = {scenario["id"]: scenario for scenario in chosen}
    results: list[ComparisonResult] = []

    if not config.AZURE_OPENAI_DEPLOYMENT:
        return [
            _not_evaluable(name, "", "no model deployment is configured to run either condition")
            for name in ("adaptive value", "retrieval influence")
        ]

    for scenario_id in ADAPTIVE_CANDIDATES:
        if scenario_id not in by_id:
            continue
        outcome = compare_adaptive(by_id[scenario_id])
        results.append(outcome)
        if outcome.differed:
            break

    if RETRIEVAL_SCENARIO in by_id:
        results.append(compare_retrieval_influence(by_id[RETRIEVAL_SCENARIO]))
    return results


def configuration_identity() -> dict[str, str]:
    """What this run ran under. Two reports are only comparable where these agree.

    The judge fields sit beside the runtime fields rather than merged into them, because the two
    models are accounted separately: the judge's tokenizer maps the same text to roughly 1.0 to
    1.35x more tokens than the runtime's, so judge token figures are not comparable with runtime
    ones and a merged accounting would invite exactly that comparison.
    """
    return {
        "model_deployment": config.AZURE_OPENAI_DEPLOYMENT or "(unset)",
        "reasoning_effort": config.REASONING_EFFORT,
        "capability_call_cap": str(config.CAPABILITY_CALL_CAP),
        "model_call_cap": str(config.MODEL_CALL_CAP),
        "investigation_deadline_s": str(config.INVESTIGATION_DEADLINE_SECONDS),
        "judge_provider": "anthropic-foundry",
        "judge_deployment": config.AZURE_CLAUDE_DEPLOYMENT or "(unset)",
        "judge_effort": JUDGE_EFFORT,
        "judge_thinking": JUDGE_THINKING,
        "judge_prompt_version": get_prompt("judge", prompts_dir=PROMPTS).version,
    }


def _judge_deployment(scenarios: list[ScenarioRun]) -> str:
    """Which deployment answered the judge, recorded even while it equals the runtime's.

    Two reports whose judgements came from different models are not comparable, and with only the
    runtime deployment on the page they would look as though they were.
    """
    answered = {s.judge_deployment for s in scenarios if s.verdicts and s.judge_deployment}
    return ", ".join(sorted(answered)) if answered else "(the judge did not run)"


# --- keeping a run --------------------------------------------------------------------------------
# The deterministic checks, by the name each prefixes its failures with. A check that named no
# failure passed. The benign check runs only where the expectation requires no immediate action.
CHECKS = ("grounding", "read-only", "absence", "outcome")
BENIGN_CHECK = "benign"
# Where a failure goes when it matches no check name above. Grouping failures by prefix is only
# faithful while every check prefixes its failures with its own name, and a check added later that
# forgets to would otherwise drop its failures silently: they would leave the evaluation, the kept
# run, and the report at once, and each would look clean. Collecting them under a name nobody
# recognizes keeps them on the page and makes the convention's breach the visible thing.
UNATTRIBUTED_CHECK = "unattributed"


def _checks(result: ScenarioResult, *, benign: bool) -> list[DeterministicCheck]:
    """Each check that ran on a scenario, as name plus pass or fail plus the failures it named.
    A scenario that did not run had no check run on it."""
    if not result.ran:
        return []
    checks = []
    claimed = [False] * len(result.failures)
    for name in (*CHECKS, BENIGN_CHECK) if benign else CHECKS:
        named = []
        for index, failure in enumerate(result.failures):
            if failure.startswith(f"{name}:"):
                named.append(failure)
                claimed[index] = True
        checks.append(DeterministicCheck(name=name, passed=not named, failures=named))

    unclaimed = [failure for index, failure in enumerate(result.failures) if not claimed[index]]
    if unclaimed:
        checks.append(DeterministicCheck(name=UNATTRIBUTED_CHECK, passed=False, failures=unclaimed))
    return checks


def _scenario_run(
    result: ScenarioResult,
    record: CompletedInvestigation | None,
    judgement: Judged,
    *,
    benign: bool = False,
) -> ScenarioRun:
    """One scenario as the kept run records it. The deterministic result and the judgement arrive
    separately and are written to separate fields; nothing here merges them."""
    verdicts = [
        JudgeVerdict(quality=quality, category=verdict.category, why=verdict.why)
        for quality, verdict in (judgement.verdicts or {}).items()
    ]
    return ScenarioRun(
        scenario_id=result.scenario_id,
        provenance=result.source.provenance.value,
        source=result.source.detail,
        ran=result.ran,
        outcome=record.outcome.value if record is not None else "",
        checks=_checks(result, benign=benign),
        notes=list(result.notes),
        verdicts=verdicts,
        judge_deployment=judgement.deployment,
        judge_note=judgement.note,
    )


def _comparison_run(comparison: ComparisonResult) -> ComparisonRun:
    return ComparisonRun(
        name=comparison.name,
        scenario_id=comparison.scenario_id,
        ran=comparison.ran,
        differences=[
            ComparisonDifference(dimension=d.dimension, detail=d.detail)
            for d in comparison.differences
        ],
        note=comparison.note,
    )


def next_run_id(kept: list[str], date: str) -> str:
    """The next identifier for a run taken on `date`: date-ordered, and unique within the day by a
    sequence after whatever is already kept for it."""
    sequences = []
    for run_id in kept:
        prefix, _, sequence = run_id.rpartition("-")
        if prefix == date and sequence.isdigit():
            sequences.append(int(sequence))
    return f"{date}-{max(sequences, default=0) + 1}"


def build_run(
    run_id: str,
    taken_at: datetime,
    label: str,
    configuration: dict[str, str],
    scenarios: list[tuple[ScenarioResult, CompletedInvestigation | None, Judged, bool]],
    comparisons: list[ComparisonResult],
) -> EvaluationRun:
    """The kept run, built from what the runner already holds. Nothing is computed that the report
    does not already carry, and no aggregate is added."""
    return EvaluationRun(
        run_id=run_id,
        taken_at=taken_at,
        label=label,
        configuration=configuration,
        scenarios=[
            _scenario_run(result, record, judgement, benign=benign)
            for result, record, judgement, benign in scenarios
        ],
        comparisons=[_comparison_run(comparison) for comparison in comparisons],
    )


def _judge_lines(scenario: ScenarioRun) -> list[str]:
    """One scenario's categories, or why there are none. Never a count and never a total: these
    are reported beside the deterministic result and are not commensurable with it.

    The qualities are printed in the rubric's own order rather than the order the verdicts happen
    to be stored in, so a recording that came back in another order still reads the same way.
    """
    if not scenario.verdicts:
        if not scenario.judge_note:
            return []
        return ["Judge: not run. " + scenario.judge_note, ""]
    by_quality = {verdict.quality: verdict for verdict in scenario.verdicts}
    lines = [f"Judge ({scenario.judge_deployment}):", ""]
    for name in (*QUALITIES, DIAGNOSIS_MATCH):
        verdict = by_quality[name]
        lines.append(f"- **{name}**: {verdict.category}. {verdict.why}")
    lines.append("")
    return lines


def _comparison_lines(comparisons: list[ComparisonRun]) -> list[str]:
    """What each comparison found. A comparison that found nothing says so: this is falsification,
    so a null result is a finding about the variable rather than a failure of the run."""
    if not comparisons:
        return []
    lines = ["## Comparisons", ""]
    for comparison in comparisons:
        where = f" on {comparison.scenario_id}" if comparison.scenario_id else ""
        lines.append(f"### {comparison.name}{where}")
        lines.append("")
        if not comparison.ran:
            lines.extend([f"Not evaluable. {comparison.note}", ""])
            continue
        if comparison.differences:
            lines.append("What differed:")
            lines.extend(f"- **{d.dimension}**: {d.detail}" for d in comparison.differences)
        else:
            lines.append("Nothing differed between the two conditions.")
        lines.append("")
        if comparison.note:
            lines.extend([f"_{comparison.note}_", ""])
    return lines


def render(run: EvaluationRun) -> str:
    """One document per run: per-scenario results with named failures, and no total.

    A view over the kept run rather than a second derivation beside it. The report and the stored
    document said the same things by walking the same inputs twice, which is a duplication that
    holds only until one of the two walks learns something the other does not; rendering from the
    document instead makes "the page shows what was kept" true by construction rather than by
    both sides being edited together.
    """
    taken_at = run.taken_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "# OpsPilot evaluation report",
        "",
        f"Run at {taken_at}.",
        "",
        "## Configuration identity",
        "",
        *(f"- **{key}**: {value}" for key, value in run.configuration.items()),
        # Beside the configured identity above: the deployment that actually answered, read from
        # the judgements themselves, so a report can show the two disagreeing.
        f"- **judge_deployment_answered**: {_judge_deployment(run.scenarios)}",
        "",
        "## Scenarios",
        "",
    ]
    for scenario in run.scenarios:
        lines.append(f"### {scenario.scenario_id} - {scenario.provenance}")
        lines.append("")
        lines.append(f"Source: {scenario.source}")
        lines.append("")
        if not scenario.ran:
            lines.extend(["Not run.", ""])
            lines.extend(_judge_lines(scenario))
            continue
        # Every failure the scenario recorded, gathered back out of the checks that claimed them.
        # Nothing can be lost on the way, because a failure no check claimed is carried by the
        # unattributed one.
        failures = [failure for check in scenario.checks for failure in check.failures]
        if failures:
            lines.append("Failed:")
            lines.extend(f"- {failure}" for failure in failures)
        else:
            lines.append("No deterministic check failed.")
        lines.append("")
        if scenario.notes:
            lines.extend([f"_{note}_" for note in scenario.notes])
            lines.append("")
        lines.extend(_judge_lines(scenario))
    lines.extend(_comparison_lines(run.comparisons))
    ran = [scenario for scenario in run.scenarios if scenario.ran]
    clean = [s for s in ran if not any(check.failures for check in s.checks)]
    lines.extend(
        [
            "## Coverage",
            "",
            f"- {len(ran)} of {len(run.scenarios)} scenario(s) ran.",
            f"- {len(clean)} of those had no deterministic failure.",
            "",
            "No composite score is reported, and none of this gates a merge.",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="every scenario, not just the fast one")
    parser.add_argument(
        "--keep",
        nargs="?",
        const="",
        default=None,
        metavar="LABEL",
        help="also write this run to the evaluation store, optionally under a label; without "
        "this the run produces its report and enters no history",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    chosen = SCENARIOS if args.full else [s for s in SCENARIOS if s["id"] == FAST_SCENARIO]
    scenarios: list[tuple[ScenarioResult, CompletedInvestigation | None, Judged, bool]] = []
    for scenario in chosen:
        scenario_id = scenario["id"]
        source = Source.for_scenario(scenario_id)
        record = obtain(scenario_id, source)
        # Deterministic first, always. The judge is asked afterwards and told none of it.
        result = evaluate(scenario_id, record, scenario["evaluation"], source)
        reported = _scenario_incident(scenario_id).short_description
        scenarios.append((result, record, judged(record, scenario, reported), False))

    if args.full:
        benign = bool(FIXTURE["evaluation"]["requires_no_immediate_action"])
        record, source = obtain_fixture(Source.for_fixture(config.AZURE_OPENAI_DEPLOYMENT))
        result = evaluate(FIXTURE["id"], record, FIXTURE["evaluation"], source, benign=benign)
        judgement = judged(record, FIXTURE, _fixture_incident().short_description)
        scenarios.append((result, record, judgement, benign))

    now = datetime.now(UTC)
    comparisons = run_comparisons(chosen) if args.full else []

    # The store is opened before the run is built, where this run is being kept, because the
    # identifier depends on what is already kept for today. A run nobody keeps is still built and
    # still rendered; it simply takes the first identifier of its date and is never written under
    # it, which is what an unkept run's identity is worth.
    store = None
    kept_ids: list[str] = []
    if args.keep is not None:
        from opspilot.evaluation.store import default_evaluation_runs

        store = default_evaluation_runs()
        kept_ids = [kept.run_id for kept in store.list_runs()]

    run = build_run(
        run_id=next_run_id(kept_ids, now.strftime("%Y-%m-%d")),
        taken_at=now,
        label=args.keep or "",
        # The configured identity, runtime and judge alike. Which deployment actually answered the
        # judge is kept per scenario, beside each judgement, so a kept run can show the two
        # disagreeing as the report does.
        configuration=configuration_identity(),
        scenarios=scenarios,
        comparisons=comparisons,
    )

    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / f"{run.taken_at.strftime('%Y-%m-%dT%H%M%SZ')}.md"
    path.write_text(render(run), encoding="utf-8")
    print(f"wrote {path.relative_to(REPO_ROOT)}")

    if store is not None:
        # Refused by the store as a duplicate if the identifier is somehow already kept, which is
        # left to raise: a kept run is never overwritten.
        store.save(run)
        print(f"kept {run.run_id}")


if __name__ == "__main__":
    main()
