"""Central configuration: eval targets and runtime settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
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
# Local dev model: qwen3:8b (~5 GB, CPU-only, has the `tools` capability) — one model
# simulates all tiers in dev. NOTE: the larger qwen3.6 (36B MoE, 23 GB) was pulled but
# won't run on this box (23 GB > 15.5 GB RAM, integrated GPU only). Build/iterate against
# gpt-4o-mini for tool-call reliability; qwen3:8b is the free local/demo path.
DEV_MODEL = _env("OPSPILOT_DEV_MODEL", "qwen3:8b")

# DEPRECATED: superseded by D-005 (the primary chat deployment is the single offline judge).
# No new consumer.
JUDGE_MODEL = _env("OPSPILOT_JUDGE_MODEL", "gpt-4.1")


# --------------------------------------------------------------------------------------
# LLM provider seam
# --------------------------------------------------------------------------------------
# Dev default = local Ollama (qwen3:8b via DEV_MODEL, the free floor). The `openai` provider
# reuses the same OpenAI-compatible client with a real key + base_url for gpt-4o-mini / Azure
# Foundry (the capability headline). `replay` plays back recorded cassettes in CI. Empty base_url
# means "the provider's default endpoint".
LLM_PROVIDER = _env("OPSPILOT_LLM_PROVIDER", "ollama")
LLM_MODEL = _env("OPSPILOT_LLM_MODEL", DEV_MODEL)
LLM_BASE_URL = _env("OPSPILOT_LLM_BASE_URL")
# Reasoning effort for reasoning models (gpt-5*, o*). `low` was too shallow — the planner skipped an
# evidence class and the sufficiency gate escalated (coverage 0.75); `medium` gives thorough enough
# tool planning while staying within the /investigate timeout. Env-tunable so the demo can dial it
# without a code change. Ignored by non-reasoning models.
REASONING_EFFORT = _env("OPSPILOT_REASONING_EFFORT", "medium")
# Sampling seed sent alongside temperature=0 on non-reasoning models. temperature=0 is NOT
# determinism: re-recording the eval against gpt-4o-mini produced byte-identical planner prompts
# and different responses.
#
# MEASURED, 2026-07-26: the seed does NOT fix that. Two recordings at this same seed produced
# different cassettes and different scorecards (evidence_recall 0.6222 vs 0.5111). OpenAI documents
# `seed` as best-effort, and on this model it is not effective. It is kept because it costs nothing,
# it is the documented mechanism if their determinism improves, and pinning it in the replay
# manifest records what was in effect. Do NOT re-run this experiment expecting a stable
# scorecard. The real instability is the sample size (3 novel scenarios) amplified by the
# planner's batched tool calls: one sampling wobble rewrites up to _MAX_BATCH actions.
#
# Note this does not make CI flaky: the committed cassette replays deterministically. The variance
# only appears when someone RE-RECORDS.
LLM_SEED = _env_int("OPSPILOT_LLM_SEED", 20260726)

# Observability span exporter: none (default, emission on, no sink until a real one is wired) |
# memory (tests) | stdout (dev). A real sink (e.g. App Insights) is not yet wired; see
# runtime-and-deployment.md for the target backend.
TRACE_EXPORTER = _env("OPSPILOT_TRACE_EXPORTER", "none")
LLM_API_KEY = _env("OPSPILOT_LLM_API_KEY") or _env("OPENAI_API_KEY")
OLLAMA_BASE_URL = _env("OPSPILOT_OLLAMA_BASE_URL", "http://localhost:11434/v1")

# Azure OpenAI (Foundry) — the production LLM path. AZURE_OPENAI_DEPLOYMENT is the *deployment* name
# the app calls (falls back to LLM_MODEL). AZURE_OPENAI_API_KEY is OPTIONAL: when it is blank the
# client authenticates keyless via the environment's managed identity (see llm/client.py).
AZURE_OPENAI_ENDPOINT = _env("AZURE_OPENAI_ENDPOINT") or _env("AZURE_FOUNDRY_ENDPOINT")
AZURE_OPENAI_API_VERSION = _env("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
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
# Reviewer / caller identity
# --------------------------------------------------------------------------------------
# Who is allowed to do what, and how that is proven. Tenant/audience/all three roles are required
# before ANY of the three auth-gated endpoints will serve — `build_reviewer_authenticator()` raises
# rather than defaulting, because every default here would weaken an access control. There is
# deliberately no setting that disables authentication; see `auth.py`'s module docstring.
#
# AZURE_TENANT_ID is the tenant whose issuer is trusted (exactly one, not a permissive set).
# OPSPILOT_API_AUDIENCE is this API's own audience — the API app's application (client) id, which
# is the `aud` claim Entra puts in the v2.0 tokens it issues for this API. It is what stops a token
# minted for a different app in the same tenant from being replayed here. (The console requests the
# scope `<audience>/.default` to obtain such a token.)
# Each *_ROLE below is an app role a principal must carry to perform that one action; authentication
# proves who, `auth.require_role`/`require_any_role` prove allowed-to-do-this-specific-thing.
ENTRA_TENANT_ID = _env("AZURE_TENANT_ID")
ENTRA_API_AUDIENCE = _env("OPSPILOT_API_AUDIENCE")
ENTRA_APPROVER_ROLE = _env("OPSPILOT_APPROVER_ROLE", "Approver")
ENTRA_SUBMIT_ROLE = _env("OPSPILOT_SUBMIT_ROLE", "Submitter")
ENTRA_READ_ROLE = _env("OPSPILOT_READ_ROLE", "Reader")
# The Entra app (client) id the operator console signs in with. Public, not a secret — it is
# embedded in the served HTML so the browser can run the MSAL authorization-code + PKCE flow.
ENTRA_CONSOLE_CLIENT_ID = _env("OPSPILOT_CONSOLE_CLIENT_ID")


# --------------------------------------------------------------------------------------
# Ingress admission control
# --------------------------------------------------------------------------------------
# A coarse cap on concurrently *running* investigations (queued/running/awaiting_approval — not yet
# terminal), checked at submission time. Bounds unbounded Azure OpenAI spend from a single caller or
# from aggregate traffic; it is deliberately a soft, best-effort check (count-then-create, not a
# distributed lock) rather than a fuller admission-control system, sufficient to close the "anyone
# can drive unlimited spend" hole without new infrastructure.
MAX_CONCURRENT_INVESTIGATIONS_PER_USER = _env_int("OPSPILOT_MAX_CONCURRENT_PER_USER", 3)
MAX_CONCURRENT_INVESTIGATIONS_GLOBAL = _env_int("OPSPILOT_MAX_CONCURRENT_GLOBAL", 20)


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
# DEPRECATED: unenforced. Reserved for reuse as the capability-call cap once something enforces it.
MAX_TOOL_CALLS = _env_int("OPSPILOT_MAX_TOOL_CALLS", 20)


# --------------------------------------------------------------------------------------
# Eval targets, defined up front, before any capability exists
# DEPRECATED: consumed only by the scenario and single-agent gates being replaced; no new consumer.
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
