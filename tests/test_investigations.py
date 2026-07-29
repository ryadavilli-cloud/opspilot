"""InMemoryInvestigationRepository — the persistence seam's own contract, independent of the API.

Covers `get_or_create`'s two guarantees the check-then-act `create()` + `find_by_idempotency_key()`
pair it replaced did not have: atomicity under concurrent callers, and an explicit rerun affordance.
"""

from __future__ import annotations

import threading

import pytest

from opspilot.investigations import (
    CommittedDecision,
    DecisionNotPendingError,
    InMemoryInvestigationRepository,
    StaleReportError,
)


def test_get_or_create_is_atomic_under_concurrent_callers():
    """N threads racing get_or_create for the SAME idempotency_key must produce exactly one
    created=True — the lock closes the window a separate find-then-create pair would leave open."""
    repo = InMemoryInvestigationRepository()
    n = 32
    results: list[tuple[object, bool]] = [None] * n  # type: ignore[list-item]

    def call(i: int) -> None:
        results[i] = repo.get_or_create(
            idempotency_key="same-key", investigation_id=f"id-{i}", incident_id="inc-1",
        )

    threads = [threading.Thread(target=call, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    created_flags = [created for _, created in results]
    assert created_flags.count(True) == 1  # exactly one caller actually created a record

    winning_id = next(rec.investigation_id for rec, created in results if created)
    assert all(rec.investigation_id == winning_id for rec, _ in results)  # everyone agrees on it


def test_get_or_create_returns_the_existing_record_without_creating_a_second():
    repo = InMemoryInvestigationRepository()
    first, first_created = repo.get_or_create(
        idempotency_key="k", investigation_id="id-1", incident_id="inc-1",
    )
    second, second_created = repo.get_or_create(
        idempotency_key="k", investigation_id="id-2", incident_id="inc-1",
    )
    assert first_created and not second_created
    assert second.investigation_id == first.investigation_id
    assert repo.get("id-2") is None  # the second caller's id was never stored


def test_force_rerun_mints_a_new_record_and_supersedes_the_key():
    repo = InMemoryInvestigationRepository()
    first, _ = repo.get_or_create(idempotency_key="k", investigation_id="id-1", incident_id="inc-1")
    rerun, rerun_created = repo.get_or_create(
        idempotency_key="k", investigation_id="id-2", incident_id="inc-1", force_rerun=True,
    )
    assert rerun_created
    assert rerun.investigation_id == "id-2" != first.investigation_id
    assert repo.get("id-1") is not None  # the superseded record is untouched, still reachable

    # A later non-forced call for the same key now returns the rerun, not the original.
    later, later_created = repo.get_or_create(
        idempotency_key="k", investigation_id="id-3", incident_id="inc-1",
    )
    assert not later_created
    assert later.investigation_id == "id-2"


# --- commit_decision: the decision leg's commit point (G-32) -------------------------------------
_HASH = "report-hash-1"


def _paused(repo: InMemoryInvestigationRepository, investigation_id: str = "id-1") -> str:
    """Drive a record to `awaiting_approval` holding `_HASH` as its pending report."""
    repo.get_or_create(
        idempotency_key=f"k-{investigation_id}",
        investigation_id=investigation_id,
        incident_id="inc-1",
    )
    repo.transition(investigation_id, "awaiting_approval", pending_interrupt={"report_hash": _HASH})
    return investigation_id


def _decision(
    decision_id: str, *, hash_: str = _HASH, fingerprint: str = "fp-1"
) -> CommittedDecision:
    return CommittedDecision(
        decision_id=decision_id,
        fingerprint=fingerprint,
        decision="approve",
        submitted_report_hash=hash_,
        approver="entra_jwt:oid-1",
        response={"investigation_id": "id-1", "status": "running", "poll_url": "/x"},
    )


def test_commit_decision_records_and_transitions_in_one_step():
    repo = InMemoryInvestigationRepository()
    investigation_id = _paused(repo)

    committed, created = repo.commit_decision(investigation_id, decision=_decision("d-1"))

    assert created and committed.decision_id == "d-1"
    record = repo.get(investigation_id)
    assert record is not None
    # The decision is durable AND the run has moved on, from a single call - there is no window
    # in which a decision is recorded but the run still looks decidable, or vice versa.
    assert record.decisions["d-1"].fingerprint == "fp-1"
    assert record.status == "running"
    assert record.pending_interrupt is None


def test_replaying_a_decision_id_returns_the_original_without_a_second_commit():
    repo = InMemoryInvestigationRepository()
    investigation_id = _paused(repo)
    repo.commit_decision(investigation_id, decision=_decision("d-1"))
    history_after_first = repo.get(investigation_id).history  # type: ignore[union-attr]

    replayed, created = repo.commit_decision(investigation_id, decision=_decision("d-1"))

    assert not created
    assert replayed.fingerprint == "fp-1"
    # No second transition: a replay must not re-drive the run.
    assert repo.get(investigation_id).history == history_after_first  # type: ignore[union-attr]


def test_a_stale_hash_is_refused_and_leaves_the_run_awaiting_approval():
    """G-32's behaviour change. The refusal must not consume the pause: the reviewer re-reads the
    current report and decides again."""
    repo = InMemoryInvestigationRepository()
    investigation_id = _paused(repo)

    with pytest.raises(StaleReportError) as excinfo:
        repo.commit_decision(investigation_id, decision=_decision("d-1", hash_="stale-hash"))

    assert excinfo.value.current_report_hash == _HASH
    record = repo.get(investigation_id)
    assert record is not None
    assert record.status == "awaiting_approval"  # still decidable
    assert record.pending_interrupt == {"report_hash": _HASH}
    assert record.decisions == {}  # nothing was committed


def test_a_decision_on_a_run_that_is_not_paused_is_refused():
    repo = InMemoryInvestigationRepository()
    repo.get_or_create(idempotency_key="k", investigation_id="id-1", incident_id="inc-1")
    repo.transition("id-1", "running")

    with pytest.raises(DecisionNotPendingError) as excinfo:
        repo.commit_decision("id-1", decision=_decision("d-1"))

    assert excinfo.value.status == "running"


def test_concurrent_distinct_decisions_commit_exactly_once():
    """N threads racing DIFFERENT decision_ids against one pause: exactly one may commit, and the
    losers must be refused rather than each resuming the graph. This is the property a
    check-then-act precondition in the endpoint would not give."""
    repo = InMemoryInvestigationRepository()
    investigation_id = _paused(repo)
    n = 16
    start = threading.Barrier(n)
    committed: list[str] = []
    refused: list[Exception] = []
    lock = threading.Lock()

    def call(i: int) -> None:
        start.wait(timeout=10)
        try:
            _, created = repo.commit_decision(
                investigation_id, decision=_decision(f"d-{i}", fingerprint=f"fp-{i}")
            )
            if created:
                with lock:
                    committed.append(f"d-{i}")
        except DecisionNotPendingError as exc:
            with lock:
                refused.append(exc)

    threads = [threading.Thread(target=call, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(committed) == 1, f"expected exactly one commit, got {committed}"
    assert len(refused) == n - 1
    record = repo.get(investigation_id)
    assert record is not None
    assert list(record.decisions) == committed  # only the winner was ever recorded
