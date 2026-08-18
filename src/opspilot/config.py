"""Central configuration: eval targets and runtime settings."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load a local, gitignored `.env` before any getenv below, a dev convenience for endpoints and
# container settings. No-op in production, where the container supplies real environment variables
# and no .env exists. Never network or heavy, just a local file read.
load_dotenv()

# --------------------------------------------------------------------------------------
# Runtime asset paths + retrieval backend
# --------------------------------------------------------------------------------------
# Local-dev defaults resolve relative to the repo. PRODUCTION sets these explicitly via env
# (the Docker image copies the corpus under /app/data and exports OPSPILOT_*_DIR): production
# MUST NOT rely on the __file__ -> data relationship, which holds only while the source tree and
# data tree share a layout. The repo-relative fallback below is a dev convenience only.
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _env(var: str, default: str = "") -> str:
    """Read an env var, tolerating a `.env` inline comment (`KEY=val  # note`) and treating a
    blank value as unset. python-dotenv keeps inline-comment text as the value, so a `.env` line
    like `AZURE_OPENAI_DEPLOYMENT=   # blank -> default` would otherwise poison config. These
    settings never legitimately contain '#'."""
    raw = os.getenv(var)
    if raw is None:
        return default
    cleaned = raw.split("#", 1)[0].strip()
    return cleaned or default


def _env_int(var: str, default: int) -> int:
    value = _env(var)
    return int(value) if value else default


def _env_float(var: str, default: float) -> float:
    value = _env(var)
    return float(value) if value else default


def _env_flag(var: str, default: bool = False) -> bool:
    value = _env(var)
    return value.lower() == "true" if value else default


def _dir_env(var: str, default: Path) -> Path:
    value = _env(var)
    return Path(value) if value else default


KB_DIR = _dir_env("OPSPILOT_KB_DIR", _REPO_ROOT / "data" / "kb")

# The one retrieval realization (D-003): Cosmos vector search + in-process lexical scoring, fused by
# reciprocal rank fusion. Not env-selectable, since there is no alternative backend to choose
# between: kept as a named constant only because `ToolService.retrieval_backend` reports it for
# readiness diagnostics.
RETRIEVAL_BACKEND = "cosmos"


# --------------------------------------------------------------------------------------
# Model seam
# --------------------------------------------------------------------------------------
# One live provider. `azure` calls the chat deployment as the environment's identity; `replay`
# plays back a recorded cassette, which is what the deterministic lane runs on.
LLM_PROVIDER = _env("OPSPILOT_LLM_PROVIDER", "azure")
# Reasoning effort for reasoning deployments. `low` was too shallow: source selection skipped an
# evidence class and the run escalated. `medium` is thorough enough while staying inside the
# request. Env-tunable so a demo can dial it without a code change.
REASONING_EFFORT = _env("OPSPILOT_REASONING_EFFORT", "medium")

# Observability span exporter: none (default, emission on, no sink until a real one is wired) |
# memory (tests) | stdout (dev). A real sink (e.g. App Insights) is not yet wired; see
# runtime-and-deployment.md for the target backend.
TRACE_EXPORTER = _env("OPSPILOT_TRACE_EXPORTER", "none")

# Azure OpenAI. AZURE_OPENAI_DEPLOYMENT names the chat deployment the app calls. No key setting
# exists: the account has local authentication disabled and the client authenticates as the
# environment's identity (see llm/client.py).
AZURE_OPENAI_ENDPOINT = _env("AZURE_OPENAI_ENDPOINT") or _env("AZURE_FOUNDRY_ENDPOINT")
AZURE_OPENAI_API_VERSION = _env("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
AZURE_OPENAI_DEPLOYMENT = _env("AZURE_OPENAI_DEPLOYMENT")

# Deployed diagnosis implementation: `deterministic` (the hand-tuned floor) or `single_agent` (the
# LLM planner + triager). The composition root builds and injects the selected pair; deterministic
# stays an EXPLICIT fallback (surfaced in /version) when single_agent is requested but its model
# cannot be built (optional `llm` deps absent, provider misconfigured, Azure endpoint unset).


# --------------------------------------------------------------------------------------


# --------------------------------------------------------------------------------------
# Durable checkpointer seam
# --------------------------------------------------------------------------------------
# Selects the LangGraph checkpointer the graph compiles with: `none` (stateless one-shot, the
# default — no behavior change), `memory` (in-process, non-durable — tests), `sqlite` (file-backed,
# durable across a process restart — local dev), or `cosmos` (Azure Cosmos DB, the production
# durable store — keyless via managed identity). The factory validates it; unknown -> ValueError.
CHECKPOINTER_BACKEND = _env("OPSPILOT_CHECKPOINTER", "none")
# Local sqlite file for the `sqlite` backend. A real path (not :memory:) so it survives a restart.
CHECKPOINTER_SQLITE_PATH = _env("OPSPILOT_CHECKPOINTER_SQLITE_PATH", ".opspilot/checkpoints.sqlite")
# Azure Cosmos DB (`cosmos` backend). Keyless: no key setting — the saver falls back to
# DefaultAzureCredential (the Container App's managed identity) when no key is provided.
COSMOS_ENDPOINT = _env("AZURE_COSMOS_ENDPOINT")
COSMOS_DATABASE = _env("AZURE_COSMOS_DATABASE", "opspilot")
COSMOS_CHECKPOINT_CONTAINER = _env("AZURE_COSMOS_CHECKPOINT_CONTAINER", "checkpoints")


# --------------------------------------------------------------------------------------
# Durable investigation-repository seam
# --------------------------------------------------------------------------------------
# Selects the async job API's InvestigationRepository backend: `memory` (in-process, non-durable —
# the default; loses every accepted/awaiting_approval record on a pod restart or scale-to-zero) or
# `cosmos` (Azure Cosmos DB — the durable, production store, keyless via managed identity). Same
# Cosmos account + database as the checkpointer above; two containers of its own. The factory
# validates it; unknown -> ValueError.
INVESTIGATION_REPOSITORY_BACKEND = _env("OPSPILOT_INVESTIGATION_REPOSITORY", "memory")
COSMOS_INVESTIGATION_CONTAINER = _env("AZURE_COSMOS_INVESTIGATION_CONTAINER", "investigations")
COSMOS_INVESTIGATION_INDEX_CONTAINER = _env(
    "AZURE_COSMOS_INVESTIGATION_INDEX_CONTAINER", "investigation-index"
)


# --------------------------------------------------------------------------------------
# RetailEase corpus: the containers corpus preparation writes and the application only reads
# --------------------------------------------------------------------------------------
# A separate database from the application's own state, so the read-only grant is scoped once at
# the database rather than enumerated per container. The application never writes here; the write
# boundary is the Cosmos role assignment, not a convention in this file.
COSMOS_RETAILEASE_DATABASE = _env("AZURE_COSMOS_RETAILEASE_DATABASE", "retailease")
COSMOS_KNOWLEDGE_CONTAINER = _env("AZURE_COSMOS_KNOWLEDGE_CONTAINER", "knowledge")
COSMOS_OPERATIONAL_RECORDS_CONTAINER = _env(
    "AZURE_COSMOS_OPERATIONAL_RECORDS_CONTAINER", "operational-records"
)

# The embedding deployment corpus preparation uses at load time and retrieval uses at query time.
# The dimension count must match the knowledge container's vector policy: Cosmos fixes it per
# embedding path, and changing it means removing and re-adding that path.
EMBEDDING_DEPLOYMENT = _env("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")
EMBEDDING_DIMENSIONS = _env_int("AZURE_OPENAI_EMBEDDING_DIMENSIONS", 1536)

# The ceiling on a single source call, in seconds. Every capability carries a deadline no greater
# than its turn's remaining time; until the turn controller owns that remaining time, this ceiling
# supplies the value. It is read by deterministic code and is unreachable from a prompt: no request
# may name its own deadline, and dispatch refuses one that tries.
SOURCE_DEADLINE_SECONDS = _env_float("OPSPILOT_SOURCE_DEADLINE_SECONDS", 10.0)

# The ceiling a governed structured query's result limit must sit at or below. The limit is always
# present in the structure; this is the bound the structure may not exceed, held in code because a
# request may not widen what it is allowed to read.
STRUCTURED_QUERY_MAX_LIMIT = _env_int("OPSPILOT_STRUCTURED_QUERY_MAX_LIMIT", 200)


# --------------------------------------------------------------------------------------
# Investigation bounds
# --------------------------------------------------------------------------------------
# The three numeric bounds one investigation runs inside, set by code at objective time and never
# widened by anything a model returns. They are read here and nowhere else, so no prompt reaches
# them: a request cannot name its own deadline, and dispatch refuses one that tries.
#
# The deadline bounds the whole run rather than any single call. Generous enough for a reasoning
# deployment to work through several gathering steps and a synthesis, short enough that an
# abandoned run does not hold a streaming request open indefinitely.
INVESTIGATION_DEADLINE_SECONDS = _env_float("OPSPILOT_INVESTIGATION_DEADLINE_SECONDS", 240.0)
# Retrieval counts against this like any other call, so it bounds what one investigation may look
# at in total rather than allowing so much per source.
CAPABILITY_CALL_CAP = _env_int("OPSPILOT_CAPABILITY_CALL_CAP", 8)
# Objective, one selection call per gathering step, synthesis, and at most one correction.
MODEL_CALL_CAP = _env_int("OPSPILOT_MODEL_CALL_CAP", 14)


# --------------------------------------------------------------------------------------
# Workflow / state versioning
# --------------------------------------------------------------------------------------
# Stamped into every investigation's state; a resuming graph checks this to route a stale
# in-flight state to a compatible reader (matters once the durable checkpointer lands).
WORKFLOW_VERSION = "1.0"


# --------------------------------------------------------------------------------------
# Environment
# --------------------------------------------------------------------------------------
ENVIRONMENT = _env("OPSPILOT_ENV", "local")  # local | dev | prod
