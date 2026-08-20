"""The offline evaluation: what it checks, and where each investigation came from.

Offline and advisory. Nothing here participates in a live run, confirms a diagnosis, or gates a
merge. It reads completed investigations and reports per scenario, each failure named, with no
composite score: a number would invite a threshold, and no threshold has a measured baseline to
stand on.

Deterministic before model-assisted. Everything code can settle, code settles here and reports pass
or fail. What needs semantic judgement is left to the judge, which runs afterwards and is reported
beside these results rather than combined with them.

The correctness checks reuse the runtime's own reference resolver and grounding function rather
than restating their rules. A second implementation of grounding would be a second definition of
what grounding means, and the one that matters is the one the runtime enforces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from opspilot.assessment.contracts import Outcome
from opspilot.grounding.gate import ground as run_gate
from opspilot.record.completed import CompletedInvestigation
from opspilot.tools import CAPABILITY_NAMES

REPO_ROOT = Path(__file__).resolve().parents[1]
CASSETTES = REPO_ROOT / "eval" / "cassettes"


class Provenance(StrEnum):
    """How one scenario's investigation was obtained, which the report must state.

    Two reports covering different scenarios look alike without it, and a comparison's result is
    uninterpretable beside a set whose coverage is unknown.
    """

    REPLAYED = "replayed"
    OBTAINED = "obtained"
    NOT_RUN = "not_run"


@dataclass(frozen=True)
class Source:
    """Where one investigation comes from, and enough detail to say which one.

    `detail` names the cassette for a replay, records that a run was live, or says why a scenario
    did not run. A scenario with no recording is reported as not run with the reason, never
    skipped silently and never counted as passing.
    """

    provenance: Provenance
    detail: str

    @classmethod
    def for_scenario(cls, scenario_id: str) -> Source:
        cassette = CASSETTES / f"{scenario_id}.json"
        if cassette.exists():
            return cls(Provenance.REPLAYED, str(cassette.relative_to(REPO_ROOT)).replace("\\", "/"))
        return cls(
            Provenance.NOT_RUN,
            f"no recording at eval/cassettes/{scenario_id}.json, and this set was not run live",
        )

    @classmethod
    def for_fixture(cls, deployment: str) -> Source:
        """The benign fixture is obtained, never replayed.

        It has no incident anyone can select and so no recording made from selecting one, and a
        recording would defeat what it tests anyway: whether a run shown something that recovered
        on its own says so, which is a live decision. Without a deployment configured it is
        reported as not run rather than quietly dropped from the set.
        """
        if deployment:
            return cls(Provenance.OBTAINED, f"run live against {deployment}")
        return cls(
            Provenance.NOT_RUN,
            "the benign fixture is never replayed and no model deployment is configured to run "
            "it live",
        )


def require_distinct(first: Source, second: Source) -> None:
    """Refuse two conditions of a controlled comparison that would read the same responses.

    A comparison exists to change one thing and watch what follows. Replaying one cassette into
    both arms returns the same model output whatever the condition, which does not show that the
    variable made no difference; it shows the variable was never applied. Enforced here rather than
    left as an instruction, because an arrangement that can be set up wrongly eventually will be.
    """
    if (
        first.provenance is Provenance.REPLAYED
        and second.provenance is Provenance.REPLAYED
        and first.detail == second.detail
    ):
        raise ValueError(
            f"both conditions of the comparison would replay {first.detail}, so the responses "
            "would be identical whatever the condition changed; record each condition separately "
            "or run them live"
        )


@dataclass
class ScenarioResult:
    """What one scenario's evaluation found. Failures are named, never counted into a score."""

    scenario_id: str
    source: Source
    failures: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ran(self) -> bool:
        return self.source.provenance is not Provenance.NOT_RUN

    @property
    def passed(self) -> bool:
        return self.ran and not self.failures


# --- deterministic correctness -------------------------------------------------------------------
def check_grounding(record: CompletedInvestigation) -> list[str]:
    """The runtime's own gate, run again over the saved record.

    The gate decides that operational support resolves in what this run admitted, that knowledge
    resolves in what it retrieved, that `what_happened` and every established candidate rest on
    admitted evidence, and that no knowledge reference stands as current proof. Re-running it here
    is the whole check: a delivered brief was grounded when it was delivered, and a record that no
    longer grounds has changed since.
    """
    admitted = {observation.evidence_ref for observation in record.observations}
    knowledge = {passage.reference for passage in record.passages}
    issues = run_gate(
        record.assessment,
        admitted_refs=admitted,
        knowledge_refs=knowledge,
        limitations=record.limitations,
    )
    return [f"grounding: {issue}" for issue in issues]


def check_no_write_was_attempted(record: CompletedInvestigation) -> list[str]:
    """Read-only, checked from what the run actually attempted rather than from intent.

    The registry holds read-only capabilities and nothing else, so an operation naming something
    outside it is either a capability that should not exist or a record that cannot be trusted.
    """
    return [
        f"read-only: the run attempted {operation.capability}, which the registry does not hold"
        for operation in record.operations
        if operation.capability not in CAPABILITY_NAMES
    ]


def check_declared_absence_is_disclosed(
    record: CompletedInvestigation, expectation: dict[str, Any]
) -> list[str]:
    """Evidence the corpus deliberately holds none of must be reported, not passed over.

    Truthfully rather than in one fixed shape: a source that answered and held nothing is an
    authoritative absence and belongs in the evidence; a source that could not answer is a
    limitation. Both are honest, and which one is correct depends on how the source behaved, so
    either satisfies this and silence satisfies neither.
    """
    failures: list[str] = []
    for absence in expectation.get("absent_evidence", []):
        capability = absence["capability"]
        disclosed_as_absence = any(
            observation.evidence_ref.startswith(f"absence:{capability}:")
            for observation in record.observations
        )
        disclosed_as_limitation = any(
            limitation.capability == capability for limitation in record.limitations
        )
        if not (disclosed_as_absence or disclosed_as_limitation):
            failures.append(
                f"absence: the corpus holds nothing for {capability} here, and the investigation "
                "neither recorded that absence nor reported it as a limitation"
            )
    return failures


# --- scenario behavior, the mechanical half ------------------------------------------------------
def check_outcome_is_accepted(
    record: CompletedInvestigation, expectation: dict[str, Any]
) -> list[str]:
    accepted = expectation["accepted_outcomes"]
    if record.outcome.value not in accepted:
        return [
            f"outcome: reported {record.outcome.value}, which this scenario does not accept "
            f"({', '.join(accepted)})"
        ]
    return []


def check_no_immediate_action(record: CompletedInvestigation) -> list[str]:
    """The benign case, where the correct answer is that nothing needs doing now.

    Affirmative rather than inferred from an empty list: saying nothing is not the same as saying
    nothing is needed, and only one of those is a useful answer to an engineer.
    """
    if any(action.now for action in record.assessment.actions):
        immediate = [action.action for action in record.assessment.actions if action.now]
        return [f"benign: recommended immediate action on a benign case: {immediate}"]
    if not record.assessment.actions:
        return ["benign: recommended nothing at all, rather than affirmatively no action now"]
    return []


def evaluate(
    scenario_id: str,
    record: CompletedInvestigation | None,
    expectation: dict[str, Any],
    source: Source,
    *,
    benign: bool = False,
) -> ScenarioResult:
    """Every deterministic check for one scenario, or the reason it was not run."""
    result = ScenarioResult(scenario_id=scenario_id, source=source)
    if record is None:
        result.notes.append(source.detail)
        return result

    result.failures.extend(check_grounding(record))
    result.failures.extend(check_no_write_was_attempted(record))
    result.failures.extend(check_declared_absence_is_disclosed(record, expectation))
    result.failures.extend(check_outcome_is_accepted(record, expectation))
    if benign:
        result.failures.extend(check_no_immediate_action(record))

    result.notes.append(f"outcome {record.outcome.value}")
    result.notes.append(
        f"{len(record.observations)} observation(s), {len(record.passages)} passage(s)"
    )
    if record.outcome is Outcome.INCONCLUSIVE:
        result.notes.append("settled no cause, which some scenarios accept")
    return result
