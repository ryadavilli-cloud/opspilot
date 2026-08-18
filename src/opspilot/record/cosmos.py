"""The Cosmos-backed Investigation Record: the durable store for local and hosted runs.

One container, one document per investigation, partitioned by `investigation_id` so a record is one
logical partition and every read is a point read. Writes are a plain create: there is one writer,
it writes once, and there is nothing to reconcile. That is what lets the duplicate refusal come
from the store itself rather than from a read-then-write check that two writers could interleave.

Cosmos requires an `id` on every document and adds its own bookkeeping properties to every read.
Neither belongs to the record, so `id` is attached on the way out and the system properties are
ignored on the way back: the model carries the design's fields and no storage artifact.
"""

from __future__ import annotations

from typing import Any

from opspilot import config
from opspilot.record.completed import CompletedInvestigation
from opspilot.record.port import AlreadySaved


class CosmosCompletedInvestigations:
    """Completed investigations in the `investigations` container.

    The container object is injected rather than constructed here, so a test holds a stand-in with
    the same surface and the deployed path holds a real Cosmos container. There is one
    implementation; only the thing being written differs.
    """

    def __init__(self, container: Any) -> None:
        self._container = container

    def save(self, record: CompletedInvestigation) -> None:
        document = record.model_dump(mode="json")
        # The identity Cosmos needs is the identity the record already has. Attaching it here keeps
        # the storage requirement out of the model without inventing a second key.
        document["id"] = record.investigation_id
        try:
            self._container.create_item(body=document)
        except Exception as exc:  # noqa: BLE001 - one writer, one write; a conflict is the refusal
            if _is_conflict(exc):
                raise AlreadySaved(record.investigation_id) from exc
            raise

    def get(self, investigation_id: str) -> CompletedInvestigation | None:
        try:
            document = self._container.read_item(
                item=investigation_id, partition_key=investigation_id
            )
        except Exception as exc:  # noqa: BLE001 - absent is an answer, not a failure
            if _is_not_found(exc):
                return None
            raise
        # Unknown keys are ignored, which is how the container's own `_rid`, `_ts`, `_etag`, and
        # `_self` stay out of the record without this having to name them.
        return CompletedInvestigation.model_validate(document)


def _status(exc: Exception) -> int | None:
    code = getattr(exc, "status_code", None)
    return code if isinstance(code, int) else None


def _is_conflict(exc: Exception) -> bool:
    return _status(exc) == 409


def _is_not_found(exc: Exception) -> bool:
    return _status(exc) == 404


def default_completed_investigations() -> CosmosCompletedInvestigations:
    """The process-wide store over the deployed container.

    The Cosmos imports are local so that importing this module needs no credential; a test that
    injects its own container never reaches this function. Keyless, like every other Cosmos client
    here: the Container App's managed identity holds write on this container and read elsewhere.
    """
    from azure.cosmos import CosmosClient
    from azure.identity import DefaultAzureCredential

    client = CosmosClient(config.COSMOS_ENDPOINT, credential=DefaultAzureCredential())
    container = client.get_database_client(config.COSMOS_DATABASE).get_container_client(
        config.COSMOS_INVESTIGATION_CONTAINER
    )
    return CosmosCompletedInvestigations(container)
