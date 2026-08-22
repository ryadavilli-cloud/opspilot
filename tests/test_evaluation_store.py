"""The kept evaluation run, and the store that keeps it.

The same three properties the investigation record is held to, asserted against both backends
through one fixture: a run survives being stored, through a real serialization; one run per
identifier, a second save refused; and the listing carries what a listing needs, newest first.
The shape itself is asserted on one point the design insists on: deterministic checks and judge
categories live in separate fields, and nothing in the document is a total.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from test_completed_record import _FakeCosmosContainer

from opspilot.evaluation.record import (
    ComparisonDifference,
    ComparisonRun,
    DeterministicCheck,
    EvaluationRun,
    JudgeVerdict,
    ScenarioRun,
)
from opspilot.evaluation.store import (
    CosmosEvaluationRuns,
    InMemoryEvaluationRuns,
    RunAlreadySaved,
)


def _run(
    run_id: str = "2026-08-21-1",
    *,
    taken_at: datetime | None = None,
    label: str = "before the prompt change",
    judge: str = "gpt-5-mini",
) -> EvaluationRun:
    """One kept run with every part populated: a replayed scenario with a failure and a judgement,
    a scenario that did not run, a comparison that differed, and one that could not be set up."""
    return EvaluationRun(
        run_id=run_id,
        taken_at=taken_at or datetime(2026, 8, 21, 14, 30, tzinfo=UTC),
        label=label,
        configuration={
            "model_deployment": "gpt-5-mini",
            "reasoning_effort": "medium",
            "capability_call_cap": "8",
            "model_call_cap": "14",
            "investigation_deadline_s": "240.0",
            "judge_deployment": judge,
            "judge_prompt_version": "judge.v1",
        },
        scenarios=[
            ScenarioRun(
                scenario_id="inc-005",
                provenance="replayed",
                source="eval/cassettes/inc-005.json",
                outcome="partial",
                checks=[
                    DeterministicCheck(name="grounding", passed=True),
                    DeterministicCheck(
                        name="outcome",
                        passed=False,
                        failures=["outcome: reported partial, which this scenario does not accept"],
                    ),
                ],
                verdicts=[
                    JudgeVerdict(quality="usefulness_and_coherence", category="meets", why="clear"),
                    JudgeVerdict(quality="diagnosis_match", category="leads", why="named it"),
                ],
                judge_deployment=judge,
            ),
            ScenarioRun(
                scenario_id="inc-001",
                provenance="not_run",
                source="no recording at eval/cassettes/inc-001.json",
                judge_note="no investigation to judge",
            ),
        ],
        comparisons=[
            ComparisonRun(
                name="adaptive value",
                scenario_id="inc-004",
                differences=[
                    ComparisonDifference(
                        dimension="required evidence",
                        detail="only the adaptive path reached deploys:checkout-api:dep-4",
                    )
                ],
            ),
            ComparisonRun(
                name="retrieval influence",
                scenario_id="inc-007",
                ran=False,
                note="a condition did not complete: the deployment was throttled",
            ),
        ],
    )


def _memory() -> InMemoryEvaluationRuns:
    return InMemoryEvaluationRuns()


def _cosmos() -> CosmosEvaluationRuns:
    return CosmosEvaluationRuns(_FakeCosmosContainer())


@pytest.fixture(params=[_memory, _cosmos], ids=["memory", "cosmos"])
def store(request):
    return request.param()


# --- a run survives being stored ----------------------------------------------------------------
def test_a_kept_run_reads_back_with_the_same_contents(store):
    original = _run()
    store.save(original)

    read_back = store.get("2026-08-21-1")

    assert read_back == EvaluationRun.model_validate(original.model_dump(mode="json"))


def test_the_read_carries_every_part_the_run_was_given(store):
    store.save(_run())
    read_back = store.get("2026-08-21-1")

    assert read_back is not None
    assert read_back.label == "before the prompt change"
    assert read_back.configuration["judge_deployment"] == "gpt-5-mini"
    assert [s.scenario_id for s in read_back.scenarios] == ["inc-005", "inc-001"]
    replayed, not_run = read_back.scenarios
    assert replayed.outcome == "partial"
    assert [(c.name, c.passed) for c in replayed.checks] == [
        ("grounding", True),
        ("outcome", False),
    ]
    assert replayed.checks[1].failures[0].startswith("outcome:")
    assert [(v.quality, v.category) for v in replayed.verdicts] == [
        ("usefulness_and_coherence", "meets"),
        ("diagnosis_match", "leads"),
    ]
    assert not_run.checks == [] and not_run.verdicts == []
    assert not_run.judge_note == "no investigation to judge"
    differed, not_evaluable = read_back.comparisons
    assert differed.ran and differed.differences[0].dimension == "required evidence"
    assert not not_evaluable.ran and "throttled" in not_evaluable.note


# --- one run per identifier ---------------------------------------------------------------------
def test_a_second_save_of_the_same_identifier_is_refused(store):
    """A kept run is a point-in-time reading. Overwriting one would replace a result someone may
    already have read with a different one under the same name."""
    store.save(_run())

    with pytest.raises(RunAlreadySaved):
        store.save(_run(label="a different reading"))

    read_back = store.get("2026-08-21-1")
    assert read_back is not None and read_back.label == "before the prompt change"


def test_reading_a_run_that_was_never_kept_is_a_clean_absence(store):
    assert store.get("2026-01-01-1") is None


# --- the listing -------------------------------------------------------------------------------
def test_an_empty_store_lists_nothing(store):
    assert store.list_runs() == []


def test_the_listing_is_newest_first_and_carries_what_a_listing_needs(store):
    """Date, label, and the configuration, because the listing has to show where one run stops
    being comparable with the one above it; not the scenarios, which are read per run."""
    store.save(_run("2026-08-20-1", taken_at=datetime(2026, 8, 20, 9, tzinfo=UTC)))
    store.save(_run("2026-08-21-1", taken_at=datetime(2026, 8, 21, 9, tzinfo=UTC), judge="gpt-x"))
    store.save(_run("2026-08-21-2", taken_at=datetime(2026, 8, 21, 15, tzinfo=UTC)))

    listed = store.list_runs()

    assert [s.run_id for s in listed] == ["2026-08-21-2", "2026-08-21-1", "2026-08-20-1"]
    assert listed[1].configuration["judge_deployment"] == "gpt-x"
    assert listed[0].label == "before the prompt change"
    assert not hasattr(listed[0], "scenarios")


# --- the shape ---------------------------------------------------------------------------------
def test_deterministic_results_and_judge_categories_are_separate_fields_and_nothing_is_a_total():
    """Never combined into one number, held by the shape rather than by remembering to. A
    scenario carries its checks in one field and its verdicts in another, and no field anywhere in
    the document is a score, a total, or a pass count."""
    fields = set(ScenarioRun.model_fields)
    assert {"checks", "verdicts"} <= fields
    every_field = {
        *EvaluationRun.model_fields,
        *ScenarioRun.model_fields,
        *DeterministicCheck.model_fields,
        *JudgeVerdict.model_fields,
        *ComparisonRun.model_fields,
    }
    assert not {name for name in every_field if any(w in name for w in ("score", "total", "count"))}


def test_the_cosmos_document_carries_the_identity_cosmos_requires_and_keeps_its_bookkeeping_out():
    container = _FakeCosmosContainer()
    store = CosmosEvaluationRuns(container)
    store.save(_run())

    document = container.documents["2026-08-21-1"]
    read_back = store.get("2026-08-21-1")

    assert document["id"] == "2026-08-21-1" and document["run_id"] == "2026-08-21-1"
    assert read_back is not None
    assert not [name for name in vars(read_back) if name.startswith("_")]
