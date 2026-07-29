"""Asynchronous investigation resource — the record, its repository seam, and an in-memory store.

The API accepts an investigation (`202 Accepted`) and runs the graph in the background, so a browser
never holds a request open for a whole investigation. This module owns the *persistence seam*: a
minimal `InvestigationRepository` the API depends on, with an in-process in-memory implementation
for this first slice. A durable implementation (Cosmos DB, alongside the LangGraph checkpointer) can
land later behind the same interface without touching the API — hence the record's `result` is a
plain JSON-able dict, not a live Pydantic object: exactly what a document store would persist.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

# queued -> running -> (awaiting_approval -> running)* -> one terminal state. `completed`/
# `degraded`/`escalated` mirror the graph's own honest terminal statuses; `failed` is a
# background-task fault (the run itself raised) — distinct from an `escalated` investigation that
# finished correctly by handing off to a human. `awaiting_approval` is NOT terminal: the graph is
# paused at `hitl_gate`'s real interrupt() (5c), holding a durable checkpoint, waiting on a
# `POST /investigations/{id}/decision` to resume it — a poller must keep polling.
InvestigationStatus = Literal[
    "queued", "running", "awaiting_approval", "completed", "degraded", "escalated", "failed"
]

TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"completed", "degraded", "escalated", "failed"}
)


def _now() -> datetime:
    return datetime.now(UTC)


class CommittedDecision(BaseModel):
    """One reviewer decision that has been durably committed against an investigation (G-32).

    Recording this IS the commit point of the decision leg: it is written in the same conditional
    update that moves `awaiting_approval -> running`, so a crash after it leaves a recorded
    decision plus a resumable checkpoint (re-drivable), never a resumed graph with no record of
    who resumed it.

    `fingerprint` is an opaque digest of the request body plus the verified reviewer, computed by
    the API. The repository never interprets it; it only stores it so a replayed `decision_id` can
    be told apart from a *different* decision reusing the same id.
    """

    decision_id: str
    fingerprint: str
    decision: str
    submitted_report_hash: str
    approver: str
    # The response body committed for this decision, replayed verbatim on a retry so a
    # double-click or a client retrying a timed-out POST cannot resume the graph twice.
    response: dict[str, Any]
    recorded_at: datetime = Field(default_factory=_now)


class InvestigationRecord(BaseModel):
    """The stored state of one async investigation. `result` is the serialized InvestigationResponse
    (a JSON-able dict) once terminal — kept untyped here so the repository stays API-agnostic."""

    investigation_id: str
    incident_id: str
    idempotency_key: str
    # The LangGraph checkpointer's `thread_id` for this investigation. Set equal to
    # `investigation_id` at creation and kept as its own named field (never conflate identifiers,
    # per this codebase's own convention) — it's what a `POST .../decision` resume must address.
    thread_id: str = ""
    # The verified Entra subject (`oid`) that submitted this investigation (Stage 8, G-57) — the
    # audit trail's submitter, and the key `count_active(subject=...)` groups by for the per-user
    # concurrency cap. `None` only for investigations pre-dating submit-endpoint auth.
    submitted_by: str | None = None
    status: InvestigationStatus = "queued"
    history: list[InvestigationStatus] = Field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
    # The raw interrupt payload from `hitl_gate` while `status == "awaiting_approval"` — the report,
    # its hash, and the safety result, for a client to review before deciding. Cleared on any
    # transition out of `awaiting_approval` so a resolved investigation never shows a stale pending
    # payload.
    pending_interrupt: dict[str, Any] | None = None
    # Every decision committed over this investigation's life, keyed by the client's `decision_id`
    # (G-32). A dict, not a single "last decision": an `edit` re-pauses and is followed by another
    # decision, and retrying the edit's id after the approve committed must replay the *edit's*
    # response, not conflict against the approve. Scoped per-investigation on purpose - a client
    # reusing a decision_id on a different investigation is isolated, not a collision.
    decisions: dict[str, CommittedDecision] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


@runtime_checkable
class InvestigationRepository(Protocol):
    """Persistence seam for async investigations. In-memory now; Cosmos DB later, same interface."""

    def get_or_create(
        self,
        *,
        idempotency_key: str,
        investigation_id: str,
        incident_id: str,
        thread_id: str = "",
        force_rerun: bool = False,
        submitted_by: str | None = None,
    ) -> tuple[InvestigationRecord, bool]: ...

    def get(self, investigation_id: str) -> InvestigationRecord | None: ...

    def transition(
        self,
        investigation_id: str,
        status: InvestigationStatus,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        pending_interrupt: dict[str, Any] | None = None,
    ) -> InvestigationRecord: ...

    def commit_decision(
        self,
        investigation_id: str,
        *,
        decision: CommittedDecision,
    ) -> tuple[CommittedDecision, bool]:
        """Atomically commit `decision` AND transition `awaiting_approval -> running` (G-32).

        Returns `(committed, created)`. `created=False` means this `decision_id` was already
        committed and `committed` is that original: the caller compares fingerprints to tell a
        harmless retry (replay the stored response) from a *different* decision reusing the id (a
        conflict). A replay is answered whatever the current status is, since a retry naturally
        arrives once the run has already moved on.

        Raises `DecisionNotPendingError` / `StaleReportError` for a decision that must not commit.
        Both checks happen INSIDE this operation rather than in the caller, so they are decided
        against the same state the write commits against - a pre-check in the endpoint would be a
        check-then-act race that lets two concurrent decisions both resume the graph.

        One write, not two: recording the decision and moving to `running` in a single conditional
        update is stronger than [§8]'s literal record-then-transition ordering. It removes the
        crash window between them, and it is what makes two concurrent *different* decision_ids
        impossible to both commit.
        """
        ...

    def count_active(self, *, subject: str | None = None) -> int:
        """Count non-terminal investigations (queued/running/awaiting_approval) — every one still
        occupying a concurrency slot. `subject=None` counts globally; otherwise only investigations
        `submitted_by` that subject."""
        ...


class InvestigationError(Exception):
    """Raised for an operation on an investigation id the repository does not know."""


class DecisionError(Exception):
    """Base for a decision the store refused to commit (G-32). Both subclasses map to a 409 and,
    critically, leave the investigation exactly as it was - a refused decision is a concurrency
    conflict, not an investigation failure, so the run stays reviewable."""


class DecisionNotPendingError(DecisionError):
    """The investigation is not `awaiting_approval`, so there is no decision to make on it."""

    def __init__(self, status: str) -> None:
        self.status = status
        super().__init__(f"investigation is not awaiting a decision (status={status})")


class StaleReportError(DecisionError):
    """The reviewer decided against a report that is no longer the one awaiting review, because a
    concurrent edit or decision advanced the thread first.

    Carries `current_report_hash` so the client can re-fetch, re-review and resubmit. The run
    REMAINS `awaiting_approval` (G-32, changing #36's escalate-on-stale): escalation is reserved
    for repeated policy failures, and losing a race is neither a policy failure nor a reason to
    burn a human's paused investigation.
    """

    def __init__(self, *, submitted: str, current_report_hash: str | None) -> None:
        self.current_report_hash = current_report_hash
        super().__init__(
            f"stale_report: decision submitted for {submitted}, "
            f"current is {current_report_hash}"
        )


class InMemoryInvestigationRepository:
    """A dict-backed repository for the first slice. Thread-safe: the background task thread writes
    transitions while request threads read, so every access holds a lock and returns a deep copy
    (callers get a consistent snapshot and cannot mutate stored state)."""

    def __init__(self) -> None:
        self._records: dict[str, InvestigationRecord] = {}
        self._by_idempotency: dict[str, str] = {}  # idempotency_key -> investigation_id
        self._lock = threading.Lock()

    def get_or_create(
        self,
        *,
        idempotency_key: str,
        investigation_id: str,
        incident_id: str,
        thread_id: str = "",
        force_rerun: bool = False,
        submitted_by: str | None = None,
    ) -> tuple[InvestigationRecord, bool]:
        """Atomically look up `idempotency_key` and create `investigation_id` only if absent — one
        lock acquisition, so two concurrent identical POSTs cannot each observe "not found" and both
        create a record (the check-then-act race the plain `create()` + `find_by_idempotency_key()`
        pair used to have).

        `force_rerun=True` skips the lookup and unconditionally makes `investigation_id` the new
        record for `idempotency_key` — the explicit rerun affordance for a reopened incident or an
        operator-requested retry. The superseded record is untouched and still reachable by its own
        id; only a later non-forced call for the same key now returns the rerun instead of it.

        Returns `(record, created)`: `created=False` means an existing investigation was returned
        and the caller's `investigation_id` was never stored — no background job may be started for
        it.
        """
        with self._lock:
            if not force_rerun:
                existing_id = self._by_idempotency.get(idempotency_key)
                if existing_id is not None:
                    return self._records[existing_id].model_copy(deep=True), False

            record = InvestigationRecord(
                investigation_id=investigation_id,
                incident_id=incident_id,
                idempotency_key=idempotency_key,
                thread_id=thread_id or investigation_id,
                status="queued",
                history=["queued"],
                submitted_by=submitted_by,
            )
            self._records[investigation_id] = record
            self._by_idempotency[idempotency_key] = investigation_id
            return record.model_copy(deep=True), True

    def get(self, investigation_id: str) -> InvestigationRecord | None:
        with self._lock:
            record = self._records.get(investigation_id)
            return record.model_copy(deep=True) if record is not None else None

    def transition(
        self,
        investigation_id: str,
        status: InvestigationStatus,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        pending_interrupt: dict[str, Any] | None = None,
    ) -> InvestigationRecord:
        with self._lock:
            record = self._records.get(investigation_id)
            if record is None:
                raise InvestigationError(f"unknown investigation {investigation_id!r}")
            record.status = status
            record.history.append(status)
            record.updated_at = _now()
            if result is not None:
                record.result = result
            if error is not None:
                record.error = error
            # Only ever non-null while paused — any transition out of awaiting_approval clears it,
            # so a resolved investigation never keeps showing a stale pending review.
            record.pending_interrupt = pending_interrupt if status == "awaiting_approval" else None
            return record.model_copy(deep=True)

    def commit_decision(
        self,
        investigation_id: str,
        *,
        decision: CommittedDecision,
    ) -> tuple[CommittedDecision, bool]:
        """See `InvestigationRepository.commit_decision`. One lock acquisition covers the replay
        lookup, both precondition checks, and the write, so the whole thing is atomic."""
        with self._lock:
            record = self._records.get(investigation_id)
            if record is None:
                raise InvestigationError(f"unknown investigation {investigation_id!r}")

            existing = record.decisions.get(decision.decision_id)
            if existing is not None:
                return existing.model_copy(deep=True), False

            if record.status != "awaiting_approval":
                raise DecisionNotPendingError(record.status)

            current_hash = (record.pending_interrupt or {}).get("report_hash")
            if decision.submitted_report_hash != current_hash:
                raise StaleReportError(
                    submitted=decision.submitted_report_hash, current_report_hash=current_hash
                )

            record.decisions[decision.decision_id] = decision.model_copy(deep=True)
            record.status = "running"
            record.history.append("running")
            record.pending_interrupt = None
            record.updated_at = _now()
            return decision.model_copy(deep=True), True

    def count_active(self, *, subject: str | None = None) -> int:
        with self._lock:
            return sum(
                1
                for record in self._records.values()
                if record.status not in TERMINAL_STATUSES
                and (subject is None or record.submitted_by == subject)
            )
