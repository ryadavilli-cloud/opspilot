"""InMemoryInvestigationRepository — the persistence seam's own contract, independent of the API.

Covers `get_or_create`'s two guarantees the check-then-act `create()` + `find_by_idempotency_key()`
pair it replaced did not have: atomicity under concurrent callers, and an explicit rerun affordance.
"""

from __future__ import annotations

import threading

from opspilot.investigations import InMemoryInvestigationRepository


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
