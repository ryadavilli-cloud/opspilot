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
    status: InvestigationStatus = "queued"
    history: list[InvestigationStatus] = Field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
    # The raw interrupt payload from `hitl_gate` while `status == "awaiting_approval"` — the report,
    # its hash, and the safety result, for a client to review before deciding. Cleared on any
    # transition out of `awaiting_approval` so a resolved investigation never shows a stale pending
    # payload.
    pending_interrupt: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


@runtime_checkable
class InvestigationRepository(Protocol):
    """Persistence seam for async investigations. In-memory now; Cosmos DB later, same interface."""

    def create(
        self, *, investigation_id: str, incident_id: str, idempotency_key: str, thread_id: str = ""
    ) -> InvestigationRecord: ...

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

    def find_by_idempotency_key(self, idempotency_key: str) -> InvestigationRecord | None: ...


class InvestigationError(Exception):
    """Raised for an operation on an investigation id the repository does not know."""


class InMemoryInvestigationRepository:
    """A dict-backed repository for the first slice. Thread-safe: the background task thread writes
    transitions while request threads read, so every access holds a lock and returns a deep copy
    (callers get a consistent snapshot and cannot mutate stored state)."""

    def __init__(self) -> None:
        self._records: dict[str, InvestigationRecord] = {}
        self._by_idempotency: dict[str, str] = {}  # idempotency_key -> investigation_id
        self._lock = threading.Lock()

    def create(
        self, *, investigation_id: str, incident_id: str, idempotency_key: str, thread_id: str = ""
    ) -> InvestigationRecord:
        record = InvestigationRecord(
            investigation_id=investigation_id,
            incident_id=incident_id,
            idempotency_key=idempotency_key,
            thread_id=thread_id or investigation_id,
            status="queued",
            history=["queued"],
        )
        with self._lock:
            self._records[investigation_id] = record
            self._by_idempotency[idempotency_key] = investigation_id
            return record.model_copy(deep=True)

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

    def find_by_idempotency_key(self, idempotency_key: str) -> InvestigationRecord | None:
        with self._lock:
            investigation_id = self._by_idempotency.get(idempotency_key)
            if investigation_id is None:
                return None
            record = self._records.get(investigation_id)
            return record.model_copy(deep=True) if record is not None else None
