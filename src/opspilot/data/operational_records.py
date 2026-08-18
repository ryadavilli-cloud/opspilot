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


def unanswered_read(exc: BaseException) -> Exception:
    """Which unanswered read this was: out of time, or unreachable.

    Classified once, here, from the client's own exception types rather than from message text. The
    builtin covers a socket or asyncio deadline; the Azure client raises its own types for a request
    or response that ran out of time, and they do not derive from the builtin. Anything else was the
    source failing to answer for some other reason, which is what unavailable means.

    The provider's exception never travels further than this: only its class name does, and only so
    a failure is diagnosable without a stack trace reaching the engineer.
    """
    if isinstance(exc, TimeoutError):
        return SourceTimedOut(type(exc).__name__)
    try:
        from azure.core.exceptions import ServiceRequestTimeoutError, ServiceResponseTimeoutError
    except ImportError:  # pragma: no cover - the client is a base dependency
        return SourceUnavailable(type(exc).__name__)
    if isinstance(exc, ServiceRequestTimeoutError | ServiceResponseTimeoutError):
        return SourceTimedOut(type(exc).__name__)
    return SourceUnavailable(type(exc).__name__)


class SourceTimedOut(Exception):
    """The read ran past the time it was given.

    Told apart from an unreachable source because the two say different things to whoever reads
    the investigation. A source that could not be reached may be down; a source that ran out of
    time was reachable and answering, and the same question asked with more room, or over a
    narrower scope, may well be answerable. Collapsing them would report a bounded run as a broken
    dependency.

    Distinct from `SourceUnavailable` rather than derived from it: they are two of the outcomes the
    result contract already separates, and a subclass would let one be caught as the other by an
    ordering mistake nothing would notice.
    """


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
            raise unanswered_read(exc) from exc

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


_default: OperationalRecords | None = None


def default_operational_records() -> OperationalRecords:
    """The process-wide reader over the deployed container (lazy, built once).

    The Cosmos imports are local so that importing this module needs no credential; a test that
    injects its own container never reaches this function. Keyless, like every other Cosmos client
    here: the Container App's managed identity holds read on the RetailEase database and no write
    to weaken.
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
