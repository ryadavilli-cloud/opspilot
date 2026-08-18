"""Read access to the `knowledge` container.

The container is partitioned by `/category`, the field that carries the three routed logical
collections (`runbook`, `architecture`, `postmortem`). Corpus preparation writes it as a setup
identity; the application only ever reads it, and holds no write permission to weaken.

Every read names the categories it searches, so a query reads only the partitions its capability
was given rather than the whole container. Query text here is authored and fixed. Values arrive
only as parameters, never spliced into text, so no caller can widen a read surface through an
argument (mirrors `operational_records.py`).
"""

from __future__ import annotations

from typing import Any

from opspilot.data.operational_records import unanswered_read

# Bound on the dense candidate set a single query returns, and on the lexical candidate set fetched
# for in-process scoring. D-003 fixes the fused-candidate ceiling at 20; both first-stage reads stay
# at or below it so fusion never has more to reconcile than the design allows.
MAX_CANDIDATES = 20

# The categories hold a few hundred passages between them at this corpus size (D-003's accepted
# trade-off), so the lexical read fetches the whole filtered scope rather than paging it.
MAX_CATEGORY_ROWS = 1000

# `c.services` is itself an array (a passage may mention several services), so "narrowed by
# service" is a set-intersection test rather than the scalar membership `ARRAY_CONTAINS` answers
# directly, hence the subquery.
_SERVICES_FILTER = (
    "AND EXISTS(SELECT VALUE s FROM s IN c.services WHERE ARRAY_CONTAINS(@services, s)) "
)


class KnowledgeRecords:
    """Read-only, category-scoped queries over the `knowledge` container.

    The container object is injected rather than constructed here, so the deployed path holds a
    real Cosmos container and a test holds a stand-in with the same `query_items` surface. There is
    one implementation of every query; only the thing being queried differs.
    """

    def __init__(self, container: Any) -> None:
        self._container = container

    def _query(
        self, text: str, parameters: list[dict[str, Any]], *, deadline_s: float
    ) -> list[Any]:
        """One read. `deadline_s` is the caller's remaining time and bounds this call; a source
        operation that outlives the turn that owns it is a bound violation even when its data is
        correct."""
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

    def by_categories(
        self, categories: tuple[str, ...], services: tuple[str, ...] | None, *, deadline_s: float
    ) -> list[dict[str, Any]]:
        """Every passage across the given categories, optionally narrowed by service: the filtered
        candidate set the in-process lexical scorer ranks (D-003)."""
        if services:
            return self._query(
                f"SELECT TOP {MAX_CATEGORY_ROWS} * FROM c "
                "WHERE ARRAY_CONTAINS(@categories, c.category) " + _SERVICES_FILTER,
                [
                    {"name": "@categories", "value": list(categories)},
                    {"name": "@services", "value": list(services)},
                ],
                deadline_s=deadline_s,
            )
        return self._query(
            f"SELECT TOP {MAX_CATEGORY_ROWS} * FROM c "
            "WHERE ARRAY_CONTAINS(@categories, c.category)",
            [{"name": "@categories", "value": list(categories)}],
            deadline_s=deadline_s,
        )

    def nearest(
        self,
        categories: tuple[str, ...],
        query_vector: list[float],
        services: tuple[str, ...] | None,
        *,
        deadline_s: float,
    ) -> list[dict[str, Any]]:
        """The dense candidate set: passages across the given categories nearest the query
        embedding, narrowed by service where given. Cosmos requires the `ORDER BY
        VectorDistance(...)` form for the vector index to serve the query; the projection carries
        the distance as `score` so the caller never recomputes it."""
        projection = (
            f"SELECT TOP {MAX_CANDIDATES} c.id, c.chunk_id, c.category, c.doc_id, c.title, "
            "c.text, c.services, c.identifiers, c.date, c.provenance, "
            "VectorDistance(c.embedding, @qv) AS score FROM c "
        )
        if services:
            return self._query(
                projection
                + "WHERE ARRAY_CONTAINS(@categories, c.category) "
                + _SERVICES_FILTER
                + "ORDER BY VectorDistance(c.embedding, @qv)",
                [
                    {"name": "@categories", "value": list(categories)},
                    {"name": "@services", "value": list(services)},
                    {"name": "@qv", "value": query_vector},
                ],
                deadline_s=deadline_s,
            )
        return self._query(
            projection + "WHERE ARRAY_CONTAINS(@categories, c.category) "
            "ORDER BY VectorDistance(c.embedding, @qv)",
            [
                {"name": "@categories", "value": list(categories)},
                {"name": "@qv", "value": query_vector},
            ],
            deadline_s=deadline_s,
        )

    def category_counts(self, categories: tuple[str, ...], *, deadline_s: float) -> dict[str, int]:
        """One count per knowledge category, for the deployment-time preparation check."""
        counts: dict[str, int] = {}
        for category in categories:
            rows = self._query(
                "SELECT VALUE COUNT(1) FROM c WHERE c.category = @category",
                [{"name": "@category", "value": category}],
                deadline_s=deadline_s,
            )
            counts[category] = int(rows[0]) if rows else 0
        return counts


_default: KnowledgeRecords | None = None


def default_knowledge_records() -> KnowledgeRecords:
    """The process-wide reader over the deployed `knowledge` container (lazy, built once).

    The Cosmos imports are local so that importing this module needs no credential; a test that
    injects its own container never reaches this function. Keyless, like every other Cosmos client
    here: the Container App's managed identity holds read on the RetailEase database and no write to
    weaken.
    """
    global _default
    if _default is None:
        from azure.cosmos import CosmosClient
        from azure.identity import DefaultAzureCredential

        from opspilot import config

        client = CosmosClient(config.COSMOS_ENDPOINT, credential=DefaultAzureCredential())
        container = client.get_database_client(
            config.COSMOS_RETAILEASE_DATABASE
        ).get_container_client(config.COSMOS_KNOWLEDGE_CONTAINER)
        _default = KnowledgeRecords(container)
    return _default
