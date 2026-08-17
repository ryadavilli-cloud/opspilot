"""Read access to the `operational-records` container.

The container is hierarchically partitioned by `/kind` then `/service`, and holds six record kinds:
`incident`, `alert`, `deployment`, `dependency`, `log`, and `metric_series`. Corpus preparation
writes it as a setup identity; the application only ever reads it, and holds no write permission to
weaken (`runtime-and-deployment.md` §10, `code-guidelines.md` §6).

Every read is partition-scoped: `kind` is always supplied, and `service` wherever the capability
knows it, so a query reads the partitions its capability owns rather than the whole container.
Narrowing that depends on value semantics rather than partitioning, notably time windows, stays in
the adapter that already owns it, so the adapter's validated parameters remain the one place a scope
is interpreted.

Query text here is authored and fixed. Values arrive only as parameters, never spliced into text,
so no caller can widen a read surface through an argument.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from opspilot import config
from opspilot.data.structured_query import StructuredQuery, translate

# A read that would return more than this is a corpus defect rather than a query to satisfy: the
# authored corpus is seven incidents. The cap is a literal, never a caller-supplied value.
MAX_ROWS = 5000

_KIND_INCIDENT = "incident"
_KIND_ALERT = "alert"
_KIND_DEPLOYMENT = "deployment"
_KIND_DEPENDENCY = "dependency"
_KIND_LOG = "log"
_KIND_METRIC_SERIES = "metric_series"

RECORD_KINDS = (
    _KIND_INCIDENT,
    _KIND_ALERT,
    _KIND_DEPLOYMENT,
    _KIND_DEPENDENCY,
    _KIND_LOG,
    _KIND_METRIC_SERIES,
)


class SourceUnavailable(Exception):
    """The source did not answer.

    Raised only by this module, and only for a failure of the container itself: a refused
    connection, a rejected request, a read that ran past its deadline. It is deliberately distinct
    from an error inside a capability's own logic, because the two axes read them differently. A
    source that could not be reached is `unavailable`; a defect in the code that queried it is
    `failed`. Collapsing them would let an unreachable container present as a broken adapter, and
    the message the engineer needs is the opposite one.

    Provider detail stops here. The message carries the exception class name only, never a
    connection string, a query, or a provider stack trace.
    """


class OperationalRecords:
    """Read-only, partition-scoped queries over the operational-records container.

    The container object is injected rather than constructed here, so the deployed path holds a real
    Cosmos container and a test holds a stand-in with the same `query_items` surface. There is one
    implementation of every query; only the thing being queried differs.
    """

    def __init__(self, container: Any) -> None:
        self._container = container

    def _query(
        self, text: str, parameters: list[dict[str, Any]], *, deadline_s: float
    ) -> list[Any]:
        """One read. `deadline_s` is the caller's remaining time and bounds this call; a source
        operation that outlives the turn that owns it is a bound violation even when its data is
        correct (`code-guidelines.md` §7)."""
        try:
            return list(
                self._container.query_items(
                    query=text,
                    parameters=parameters,
                    enable_cross_partition_query=True,
                    timeout=deadline_s,
                )
            )
        except Exception as exc:  # noqa: BLE001 - every container failure is one unanswered read
            raise SourceUnavailable(type(exc).__name__) from exc

    def incident(self, incident_id: str, *, deadline_s: float) -> dict[str, Any] | None:
        rows = self._query(
            f"SELECT TOP {MAX_ROWS} * FROM c WHERE c.kind = @kind AND c.incident_id = @incident_id",
            [
                {"name": "@kind", "value": _KIND_INCIDENT},
                {"name": "@incident_id", "value": incident_id},
            ],
            deadline_s=deadline_s,
        )
        return rows[0] if rows else None

    def incidents(self, incident_ids: list[str], *, deadline_s: float) -> list[dict[str, Any]]:
        """Several incidents in one read. A caller holding a set of ids issues one bounded call
        rather than one per id: reads issued together share the deadline they were given, and a
        fan-out of single reads under the same deadline can exceed it in aggregate while each
        individual call stays inside it."""
        if not incident_ids:
            return []
        return self._query(
            f"SELECT TOP {MAX_ROWS} * FROM c "
            "WHERE c.kind = @kind AND ARRAY_CONTAINS(@incident_ids, c.incident_id)",
            [
                {"name": "@kind", "value": _KIND_INCIDENT},
                {"name": "@incident_ids", "value": list(incident_ids)},
            ],
            deadline_s=deadline_s,
        )

    def alerts_for(self, incident_id: str, *, deadline_s: float) -> list[dict[str, Any]]:
        return self._query(
            f"SELECT TOP {MAX_ROWS} * FROM c WHERE c.kind = @kind AND c.incident_id = @incident_id",
            [
                {"name": "@kind", "value": _KIND_ALERT},
                {"name": "@incident_id", "value": incident_id},
            ],
            deadline_s=deadline_s,
        )

    def alerts(self, service: str, *, deadline_s: float) -> list[dict[str, Any]]:
        """Every alert a service raised. Scoped by service rather than by incident, because an
        alert reference names the service that raised it and the alert's own identifier, and
        resolving one must not need the incident it was later correlated to."""
        return self._query(
            f"SELECT TOP {MAX_ROWS} * FROM c WHERE c.kind = @kind AND c.service = @service",
            [{"name": "@kind", "value": _KIND_ALERT}, {"name": "@service", "value": service}],
            deadline_s=deadline_s,
        )

    def deployments(self, services: list[str], *, deadline_s: float) -> list[dict[str, Any]]:
        return self._query(
            f"SELECT TOP {MAX_ROWS} * FROM c "
            "WHERE c.kind = @kind AND ARRAY_CONTAINS(@services, c.service)",
            [
                {"name": "@kind", "value": _KIND_DEPLOYMENT},
                {"name": "@services", "value": list(services)},
            ],
            deadline_s=deadline_s,
        )

    def logs(self, service: str, *, deadline_s: float) -> list[dict[str, Any]]:
        return self._query(
            f"SELECT TOP {MAX_ROWS} * FROM c WHERE c.kind = @kind AND c.service = @service",
            [{"name": "@kind", "value": _KIND_LOG}, {"name": "@service", "value": service}],
            deadline_s=deadline_s,
        )

    def metric_series(self, service: str, *, deadline_s: float) -> list[dict[str, Any]]:
        return self._query(
            f"SELECT TOP {MAX_ROWS} * FROM c WHERE c.kind = @kind AND c.service = @service",
            [
                {"name": "@kind", "value": _KIND_METRIC_SERIES},
                {"name": "@service", "value": service},
            ],
            deadline_s=deadline_s,
        )

    def edges(self, *, deadline_s: float) -> list[dict[str, Any]]:
        return self._query(
            f"SELECT TOP {MAX_ROWS} * FROM c WHERE c.kind = @kind",
            [{"name": "@kind", "value": _KIND_DEPENDENCY}],
            deadline_s=deadline_s,
        )

    def structured(self, query: StructuredQuery, *, deadline_s: float) -> list[Any]:
        """Execute a validated query structure.

        Takes the structure rather than text, and translates it here, so no path exists through
        which a caller could hand this reader a query of its own. `validate` runs before this, at
        the capability boundary, because a rejection has to become a limitation rather than an
        exception crossing the source.
        """
        text, parameters = translate(query)
        return self._query(text, parameters, deadline_s=deadline_s)

    def kind_counts(self, *, deadline_s: float) -> dict[str, int]:
        """One count per record kind, for the deployment-time preparation check. Absent preparation
        must present as a deployment failure rather than as an empty answer at turn time, and a
        container holding only some kinds would break the capabilities whose kind is missing."""
        counts: dict[str, int] = {}
        for kind in RECORD_KINDS:
            rows = self._query(
                "SELECT VALUE COUNT(1) FROM c WHERE c.kind = @kind",
                [{"name": "@kind", "value": kind}],
                deadline_s=deadline_s,
            )
            counts[kind] = int(rows[0]) if rows else 0
        return counts


@dataclass(frozen=True)
class PreparationStatus:
    """Which record kinds the container holds, and which it is missing.

    Every kind is reported together rather than one failure at a time, so an operator reading a
    failed readiness probe sees the whole shortfall in one response.
    """

    counts: dict[str, int]
    missing: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.missing


def preparation_status(records: OperationalRecords, *, deadline_s: float) -> PreparationStatus:
    """Whether corpus preparation has run against the container this application reads.

    A kind holding zero records is missing, not empty: the capability that owns it could only ever
    answer with nothing, which would read downstream as an authoritative absence rather than as an
    unprepared deployment. Raises `SourceUnavailable` when the container cannot be reached, which
    the readiness probe converts into a failed check rather than a ready one.
    """
    counts = records.kind_counts(deadline_s=deadline_s)
    return PreparationStatus(
        counts=counts, missing=tuple(kind for kind in RECORD_KINDS if not counts.get(kind))
    )


_default: OperationalRecords | None = None


def default_operational_records() -> OperationalRecords:
    """The process-wide reader over the deployed container (lazy, built once).

    The Cosmos imports are local so that importing this module needs neither the optional
    `checkpoint` dependency group nor a credential; a test that injects its own container never
    reaches this function. Keyless, like every other Cosmos client here: the Container App's
    managed identity holds read on the RetailEase database and no write to weaken.
    """
    global _default
    if _default is None:
        from azure.cosmos import CosmosClient
        from azure.identity import DefaultAzureCredential

        client = CosmosClient(config.COSMOS_ENDPOINT, credential=DefaultAzureCredential())
        container = client.get_database_client(
            config.COSMOS_RETAILEASE_DATABASE
        ).get_container_client(config.COSMOS_OPERATIONAL_RECORDS_CONTAINER)
        _default = OperationalRecords(container)
    return _default
