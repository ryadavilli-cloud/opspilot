"""Central configuration: eval targets, severity->model routing, and runtime settings.

All quality targets are defined here *up front* (before any capability exists) so every
phase builds against a fixed bar. The severity->tier map is the cost/value lever: cheap
models handle the high-volume low-severity tail; the strong model is reserved for the rare
high-severity case. Concrete models are resolved per environment, keeping the core
provider-agnostic (local dev uses one model to simulate all tiers).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from dotenv import load_dotenv

# Load a local, gitignored `.env` before any getenv below (dev convenience for keys like
# OPENAI_API_KEY). No-op in production, where the container supplies real environment variables and
# no .env exists. Never network or heavy — just a local file read.
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
    like `OPSPILOT_LLM_MODEL=   # blank -> default` would otherwise poison config. These settings
    never legitimately contain '#'."""
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


CORPUS_DIR = _dir_env("OPSPILOT_CORPUS_DIR", _REPO_ROOT / "data" / "synthetic")
KB_DIR = _dir_env("OPSPILOT_KB_DIR", _REPO_ROOT / "data" / "kb")
DISTRACTOR_DIR = _dir_env("OPSPILOT_DISTRACTOR_DIR", _REPO_ROOT / "data" / "distractors")

# Retrieval backend: `hybrid` (dense + BM25, local/eval) or `bm25` (lexical-only, the runtime
# image default — no embedding model download). Selected by env; validated by the factory.
RETRIEVAL_BACKEND = _env("OPSPILOT_RETRIEVAL_BACKEND", "hybrid")


# --------------------------------------------------------------------------------------
# Severity & model tiers
# --------------------------------------------------------------------------------------
class Severity(StrEnum):
    SEV1 = "SEV1"
    SEV2 = "SEV2"
    SEV3 = "SEV3"
    SEV4 = "SEV4"


class Tier(StrEnum):
    CHEAP = "cheap"        # high-volume low-sev long tail
    STANDARD = "standard"  # default workhorse + SEV1 ceiling
    PREMIUM = "premium"    # flag-gated, production-only, off by default


# Default ceiling is STANDARD (Sonnet). PREMIUM (Opus) is only reachable when
# ENABLE_OPUS_SEV1 is set in production — see resolve_tier().
SEVERITY_TIER: dict[Severity, Tier] = {
    Severity.SEV4: Tier.CHEAP,
    Severity.SEV3: Tier.CHEAP,
    Severity.SEV2: Tier.STANDARD,
    Severity.SEV1: Tier.STANDARD,
}

# Concrete models per environment. Prod = severity-tiered Claude on Azure Foundry;
# dev = one local model (Ollama) simulating every tier.
PROD_MODELS: dict[Tier, str] = {
    Tier.CHEAP: "claude-haiku-4-5",
    Tier.STANDARD: "claude-sonnet-4-6",
    Tier.PREMIUM: "claude-opus-4-8",
}

# Local dev model: qwen3:8b (~5 GB, CPU-only, has the `tools` capability) — one model
# simulates all tiers in dev. NOTE: the larger qwen3.6 (36B MoE, 23 GB) was pulled but
# won't run on this box (23 GB > 15.5 GB RAM, integrated GPU only). Build/iterate against
# gpt-4o-mini for tool-call reliability; qwen3:8b is the free local/demo path.
DEV_MODEL = _env("OPSPILOT_DEV_MODEL", "qwen3:8b")

# Pinned, cross-vendor judge (>= system strength). Kept fixed so eval scores stay
# comparable across runs. SEV1 escalates to a two-judge panel if parity is in doubt.
JUDGE_MODEL = _env("OPSPILOT_JUDGE_MODEL", "gpt-4.1")

# Opus tier is OFF by default — reserved, not run in the demo deployment.
ENABLE_OPUS_SEV1 = _env_flag("OPSPILOT_ENABLE_OPUS_SEV1")


def resolve_tier(severity: Severity) -> Tier:
    """Map a severity to its model tier, honoring the flag-gated Opus escalation."""
    tier = SEVERITY_TIER[severity]
    if severity is Severity.SEV1 and ENABLE_OPUS_SEV1:
        return Tier.PREMIUM
    return tier


# --------------------------------------------------------------------------------------
# LLM provider seam (Stage 4)
# --------------------------------------------------------------------------------------
# Dev default = local Ollama (qwen3:8b via DEV_MODEL, the free floor). The `openai` provider
# reuses the same OpenAI-compatible client with a real key + base_url for gpt-4o-mini / Azure
# Foundry (the capability headline). `replay` plays back recorded cassettes in CI. Empty base_url
# means "the provider's default endpoint".
LLM_PROVIDER = _env("OPSPILOT_LLM_PROVIDER", "ollama")
LLM_MODEL = _env("OPSPILOT_LLM_MODEL", DEV_MODEL)
LLM_BASE_URL = _env("OPSPILOT_LLM_BASE_URL")
LLM_API_KEY = _env("OPSPILOT_LLM_API_KEY") or _env("OPENAI_API_KEY")
OLLAMA_BASE_URL = _env("OPSPILOT_OLLAMA_BASE_URL", "http://localhost:11434/v1")

# Azure OpenAI (Foundry) — the production LLM path. AZURE_OPENAI_DEPLOYMENT is the *deployment* name
# the app calls (falls back to LLM_MODEL). AZURE_OPENAI_API_KEY is OPTIONAL: when it is blank the
# client authenticates keyless via the environment's managed identity (see llm/client.py).
AZURE_OPENAI_ENDPOINT = _env("AZURE_OPENAI_ENDPOINT") or _env("AZURE_FOUNDRY_ENDPOINT")
AZURE_OPENAI_API_VERSION = _env("AZURE_OPENAI_API_VERSION", "2024-10-21")
AZURE_OPENAI_API_KEY = _env("AZURE_OPENAI_API_KEY") or _env("AZURE_FOUNDRY_API_KEY")
AZURE_OPENAI_DEPLOYMENT = _env("AZURE_OPENAI_DEPLOYMENT")

# Deployed diagnosis implementation: `deterministic` (the hand-tuned floor) or `single_agent` (the
# LLM planner + triager). The composition root builds and injects the selected pair; deterministic
# stays an EXPLICIT fallback (surfaced in /version) when single_agent is requested but its model
# cannot be built (optional `llm` deps absent, provider misconfigured, Azure endpoint unset).
IMPLEMENTATION = _env("OPSPILOT_IMPLEMENTATION", "deterministic")


# --------------------------------------------------------------------------------------
# Retrieval / embedding models
# --------------------------------------------------------------------------------------
EMBEDDING_MODEL = "BAAI/bge-m3"               # dense + sparse in one model
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"

# Depth of the first-stage (hybrid) candidate set handed to the cross-encoder reranker.
# Deeper = higher recall into the rerank stage at a linear cost in cross-encoder calls.
RERANK_CANDIDATES = _env_int("OPSPILOT_RERANK_CANDIDATES", 30)


# --------------------------------------------------------------------------------------
# Durable checkpointer seam (Stage 5b)
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
# Durable investigation-repository seam (Stage 5c, pulled forward from Stage 8's shared Cosmos
# account)
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
# Reviewer identity (Stage 5e, G-01)
# --------------------------------------------------------------------------------------
# Who is allowed to approve a report, and how that is proven. All three are required before the
# decision endpoint will serve — `build_reviewer_authenticator()` raises rather than defaulting,
# because every default here would weaken a publication control. There is deliberately no setting
# that disables authentication; see `auth.py`'s module docstring.
#
# AZURE_TENANT_ID is the tenant whose issuer is trusted (exactly one, not a permissive set).
# OPSPILOT_API_AUDIENCE is this API's own audience — the API app's application (client) id, which
# is the `aud` claim Entra puts in the v2.0 tokens it issues for this API. It is what stops a token
# minted for a different app in the same tenant from being replayed here. (The console requests the
# scope `<audience>/.default` to obtain such a token.)
# OPSPILOT_APPROVER_ROLE is the app role a principal must carry to decide; authentication proves
# who, this proves allowed-to-publish.
ENTRA_TENANT_ID = _env("AZURE_TENANT_ID")
ENTRA_API_AUDIENCE = _env("OPSPILOT_API_AUDIENCE")
ENTRA_APPROVER_ROLE = _env("OPSPILOT_APPROVER_ROLE", "Approver")
# The Entra app (client) id the operator console signs in with. Public, not a secret — it is
# embedded in the served HTML so the browser can run the MSAL authorization-code + PKCE flow.
ENTRA_CONSOLE_CLIENT_ID = _env("OPSPILOT_CONSOLE_CLIENT_ID")


# --------------------------------------------------------------------------------------
# Workflow / state versioning
# --------------------------------------------------------------------------------------
# Stamped into every investigation's state; a resuming graph checks this to route a stale
# in-flight state to a compatible reader (matters once the durable checkpointer lands).
WORKFLOW_VERSION = "1.0"


# --------------------------------------------------------------------------------------
# Agentic loop controls (circuit breakers)
# --------------------------------------------------------------------------------------
MAX_DIAGNOSE_ITERS = _env_int("OPSPILOT_MAX_DIAGNOSE_ITERS", 5)
CONFIDENCE_THRESHOLD = _env_float("OPSPILOT_CONFIDENCE_THRESHOLD", 0.75)
MAX_TOOL_CALLS = _env_int("OPSPILOT_MAX_TOOL_CALLS", 20)


# --------------------------------------------------------------------------------------
# Eval targets — defined up front, gated per the execution plan
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class EvalTargets:
    # Retrieval
    mrr_min: float = 0.80
    precision_at_k: int = 5
    # Routing
    routing_accuracy_min: float = 0.95
    # Faithfulness / generation
    groundedness_min: float = 0.85
    completeness_min: float = 0.75
    answer_relevance_min: float = 0.80
    # Correctness / quality
    correctness_min: float = 0.80
    actionability_min: float = 0.70  # G-Eval domain criterion
    # Safety
    pii_leak_rate_max: float = 0.0
    # Performance
    fast_path_p95_seconds: float = 3.0
    full_investigation_p95_seconds: float = 45.0


TARGETS = EvalTargets()


# --------------------------------------------------------------------------------------
# Runtime environment
# --------------------------------------------------------------------------------------
ENVIRONMENT = _env("OPSPILOT_ENV", "local")  # local | dev | prod
LANGSMITH_ENABLED = _env_flag("LANGSMITH_TRACING")
