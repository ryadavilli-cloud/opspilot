"""Azure Cosmos DB-backed InvestigationRepository — the durable production store for the async job
API (Stage 5c, pulled forward from Stage 8's shared Cosmos account). Implements the same
`InvestigationRepository` seam as `InMemoryInvestigationRepository`; `api.py` does not know which
one it is talking to.

Two containers, mirroring the in-memory repository's two dicts:
  - the records container: id = investigation_id, holds the full `InvestigationRecord`.
  - the index container:   id = idempotency_key, holds just `{"investigation_id": ...}`.

Cosmos enforces `id` uniqueness within a container, so a plain `create_item` on the index container
for `id=idempotency_key` is an atomic, cross-replica compare-and-swap — the guarantee
`InMemoryInvestigationRepository`'s `threading.Lock` cannot give once the app runs more than one
replica (each replica has its own lock, its own process, its own dict). `transition()` uses
Cosmos's ETag optimistic concurrency (a conditional `replace_item`) for the same reason.

The two-write `get_or_create` (record first, index second) is deliberately ordered so a crash
between them leaves at most a harmless orphaned record — never an index pointing at a record that
was never written: the record is created first with a fresh, never-yet-shared id, so its own
`create_item` can never conflict; only the index `create_item` can lose the race, and a loser's
record simply stays unreferenced by any idempotency_key.

Keyless: `DefaultAzureCredential`, mirroring `checkpoint.py`'s `cosmos` backend and
`CosmosDBSaverSync` — no key is ever configured or stored.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from azure.core import MatchConditions
from azure.cosmos import CosmosClient, PartitionKey, exceptions
from azure.identity import DefaultAzureCredential

from opspilot.investigations import InvestigationError, InvestigationRecord, InvestigationStatus

# Re-reads and reapplies a transition this many times before giving up on the ETag race — a single
# investigation is resumed/transitioned by one background task at a time in normal operation, so
# sustained contention here would itself indicate a bug, not expected concurrency.
_MAX_TRANSITION_RETRIES = 5


def _now() -> datetime:
    return datetime.now(UTC)


class CosmosInvestigationRepository:
    """A Cosmos DB-backed repository. Databases/containers are self-provisioned on first use (like
    `CosmosDBSaverSync`), so nothing about this document schema lives in `infra/main.bicep` — only
    the account and its data-plane RBAC grant do."""

    def __init__(
        self,
        *,
        endpoint: str,
        database_name: str,
        records_container_name: str,
        index_container_name: str,
    ) -> None:
        self._client = CosmosClient(endpoint, credential=DefaultAzureCredential())
        database = self._client.create_database_if_not_exists(database_name)
        self._records = database.create_container_if_not_exists(
            id=records_container_name, partition_key=PartitionKey(path="/investigation_id"),
        )
        self._index = database.create_container_if_not_exists(
            id=index_container_name, partition_key=PartitionKey(path="/id"),
        )

    def _read_record(self, investigation_id: str) -> InvestigationRecord:
        doc = self._records.read_item(item=investigation_id, partition_key=investigation_id)
        return InvestigationRecord.model_validate(doc)

    def get_or_create(
        self,
        *,
        idempotency_key: str,
        investigation_id: str,
        incident_id: str,
        thread_id: str = "",
        force_rerun: bool = False,
    ) -> tuple[InvestigationRecord, bool]:
        record = InvestigationRecord(
            investigation_id=investigation_id,
            incident_id=incident_id,
            idempotency_key=idempotency_key,
            thread_id=thread_id or investigation_id,
            status="queued",
            history=["queued"],
        )
        self._records.create_item(body=record.model_dump(mode="json"))

        if force_rerun:
            self._index.upsert_item({"id": idempotency_key, "investigation_id": investigation_id})
            return record, True

        try:
            self._index.create_item(
                body={"id": idempotency_key, "investigation_id": investigation_id}
            )
            return record, True
        except exceptions.CosmosResourceExistsError:
            # Another caller's get_or_create won the race for this key first. Our own record above
            # is now a harmless orphan: created=False tells this caller not to start a background
            # job, and nothing else will ever look it up (no index entry points at it).
            winner_id = self._index.read_item(
                item=idempotency_key, partition_key=idempotency_key
            )["investigation_id"]
            return self._read_record(winner_id), False

    def get(self, investigation_id: str) -> InvestigationRecord | None:
        try:
            return self._read_record(investigation_id)
        except exceptions.CosmosResourceNotFoundError:
            return None

    def transition(
        self,
        investigation_id: str,
        status: InvestigationStatus,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        pending_interrupt: dict[str, Any] | None = None,
    ) -> InvestigationRecord:
        for _ in range(_MAX_TRANSITION_RETRIES):
            try:
                doc = self._records.read_item(
                    item=investigation_id, partition_key=investigation_id
                )
            except exceptions.CosmosResourceNotFoundError as exc:
                raise InvestigationError(f"unknown investigation {investigation_id!r}") from exc

            etag = doc["_etag"]
            record = InvestigationRecord.model_validate(doc)
            record.status = status
            record.history.append(status)
            record.updated_at = _now()
            if result is not None:
                record.result = result
            if error is not None:
                record.error = error
            record.pending_interrupt = pending_interrupt if status == "awaiting_approval" else None

            try:
                self._records.replace_item(
                    item=investigation_id,
                    body=record.model_dump(mode="json"),
                    etag=etag,
                    match_condition=MatchConditions.IfNotModified,
                )
                return record
            except exceptions.CosmosAccessConditionFailedError:
                continue  # someone else transitioned it first — re-read and reapply

        raise InvestigationError(
            f"transition for {investigation_id!r} lost the optimistic-concurrency race "
            f"{_MAX_TRANSITION_RETRIES} times in a row"
        )
