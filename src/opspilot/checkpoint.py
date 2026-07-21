"""Checkpointer factory — selects a durable LangGraph checkpointer from config/env.

The seam the HITL interrupt (5c) and the async-202 job API (5d) build on: a real, durable saver so a
paused or in-flight investigation survives a process restart and resumes from the exact checkpoint.

Backends:
  - ``none``   — no checkpointer (stateless one-shot; the default, no behavior change).
  - ``memory`` — in-process ``MemorySaver`` (non-durable; tests only).
  - ``sqlite`` — file-backed ``SqliteSaver`` (durable across a restart; local dev + the CI gate).
  - ``cosmos`` — Azure Cosmos DB ``CosmosDBSaverSync`` (the production store), keyless: no key is
    passed, so the saver falls back to ``DefaultAzureCredential`` (the Container App's managed
    identity), mirroring the Azure OpenAI path.

Unknown backend -> ``ValueError``, like the retrieval / chat-model / planner factories: fail loud
rather than silently run a different (or non-durable) store than the caller asked for. The heavy /
optional imports (sqlite, cosmos SDK) are lazy, so importing this module costs nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from opspilot import config

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver

_KNOWN = ("none", "memory", "sqlite", "cosmos")


def build_checkpointer(
    backend: str | None = None, *, sqlite_path: str | None = None
) -> BaseCheckpointSaver | None:
    """Build the checkpointer for `backend` (default: `config.CHECKPOINTER_BACKEND`).

    Returns ``None`` for the ``none`` backend (a checkpointer-less graph). `sqlite_path` overrides
    `config.CHECKPOINTER_SQLITE_PATH` (the CI gate points it at a tmp file). Unknown -> ValueError.
    """
    backend = (backend or config.CHECKPOINTER_BACKEND).lower()

    if backend == "none":
        return None

    if backend == "memory":
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()

    if backend == "sqlite":
        import sqlite3

        from langgraph.checkpoint.sqlite import SqliteSaver

        path = Path(sqlite_path or config.CHECKPOINTER_SQLITE_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: one long-lived connection shared across the app's worker threads.
        saver = SqliteSaver(sqlite3.connect(str(path), check_same_thread=False))
        saver.setup()  # idempotent — create the checkpoint tables if they do not exist yet
        return saver

    if backend == "cosmos":
        # Validate cheap config before the optional import, so a missing endpoint fails with a clear
        # ValueError even where the `checkpoint` group is not installed (e.g. the CI lanes).
        if not config.COSMOS_ENDPOINT:
            raise ValueError("the 'cosmos' checkpointer requires AZURE_COSMOS_ENDPOINT")

        from langchain_azure_cosmosdb import CosmosDBSaverSync  # lazy: optional `checkpoint` group

        # Keyless: omit `key` so the saver authenticates with DefaultAzureCredential (the Container
        # App's managed identity on Azure, `az login` locally) — no key stored anywhere.
        return CosmosDBSaverSync(
            endpoint=config.COSMOS_ENDPOINT,
            database_name=config.COSMOS_DATABASE,
            container_name=config.COSMOS_CHECKPOINT_CONTAINER,
        )

    raise ValueError(f"unknown checkpointer backend {backend!r}; known: {', '.join(_KNOWN)}")
