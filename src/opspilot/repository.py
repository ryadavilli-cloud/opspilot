"""Investigation-repository factory — selects the async job API's persistence backend from
config/env, mirroring `checkpoint.py`'s factory shape exactly.

Backends:
  - ``memory`` — in-process ``InMemoryInvestigationRepository`` (the default; loses every
    accepted/awaiting_approval record on a pod restart, redeploy, or scale-to-zero — and, with more
    than one replica, a poll can land on a replica that never ran the job).
  - ``cosmos`` — Azure Cosmos DB (``CosmosInvestigationRepository``), keyless: no key is passed,
    so it falls back to ``DefaultAzureCredential`` (the Container App's managed identity),
    mirroring the checkpointer's ``cosmos`` backend and the Azure OpenAI path.

Unknown backend -> ``ValueError``, like the retrieval / chat-model / planner / checkpointer
factories: fail loud rather than silently run a different (or non-durable) store than the caller
asked for. The optional Cosmos SDK import is lazy, so importing this module costs nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from opspilot import config
from opspilot.investigations import InMemoryInvestigationRepository

if TYPE_CHECKING:
    from opspilot.investigations import InvestigationRepository

_KNOWN = ("memory", "cosmos")


def build_investigation_repository(backend: str | None = None) -> InvestigationRepository:
    """Build the investigation repository for `backend` (default:
    `config.INVESTIGATION_REPOSITORY_BACKEND`). Unknown -> ValueError.
    """
    backend = (backend or config.INVESTIGATION_REPOSITORY_BACKEND).lower()

    if backend == "memory":
        return InMemoryInvestigationRepository()

    if backend == "cosmos":
        if not config.COSMOS_ENDPOINT:
            raise ValueError(
                "the 'cosmos' investigation repository requires AZURE_COSMOS_ENDPOINT"
            )

        from opspilot.cosmos_investigations import CosmosInvestigationRepository

        return CosmosInvestigationRepository(
            endpoint=config.COSMOS_ENDPOINT,
            database_name=config.COSMOS_DATABASE,
            records_container_name=config.COSMOS_INVESTIGATION_CONTAINER,
            index_container_name=config.COSMOS_INVESTIGATION_INDEX_CONTAINER,
        )

    raise ValueError(
        f"unknown investigation repository backend {backend!r}; known: {', '.join(_KNOWN)}"
    )
