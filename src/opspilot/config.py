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
DEV_MODEL = os.getenv("OPSPILOT_DEV_MODEL", "qwen3:8b")

# Pinned, cross-vendor judge (>= system strength). Kept fixed so eval scores stay
# comparable across runs. SEV1 escalates to a two-judge panel if parity is in doubt.
JUDGE_MODEL = os.getenv("OPSPILOT_JUDGE_MODEL", "gpt-4.1")

# Opus tier is OFF by default — reserved, not run in the demo deployment.
ENABLE_OPUS_SEV1 = os.getenv("OPSPILOT_ENABLE_OPUS_SEV1", "false").lower() == "true"


def resolve_tier(severity: Severity) -> Tier:
    """Map a severity to its model tier, honoring the flag-gated Opus escalation."""
    tier = SEVERITY_TIER[severity]
    if severity is Severity.SEV1 and ENABLE_OPUS_SEV1:
        return Tier.PREMIUM
    return tier


# --------------------------------------------------------------------------------------
# Retrieval / embedding models
# --------------------------------------------------------------------------------------
EMBEDDING_MODEL = "BAAI/bge-m3"               # dense + sparse in one model
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"

# Depth of the first-stage (hybrid) candidate set handed to the cross-encoder reranker.
# Deeper = higher recall into the rerank stage at a linear cost in cross-encoder calls.
RERANK_CANDIDATES = int(os.getenv("OPSPILOT_RERANK_CANDIDATES", "30"))


# --------------------------------------------------------------------------------------
# Workflow / state versioning
# --------------------------------------------------------------------------------------
# Stamped into every investigation's state; a resuming graph checks this to route a stale
# in-flight state to a compatible reader (matters once the durable checkpointer lands).
WORKFLOW_VERSION = "1.0"


# --------------------------------------------------------------------------------------
# Agentic loop controls (circuit breakers)
# --------------------------------------------------------------------------------------
MAX_DIAGNOSE_ITERS = int(os.getenv("OPSPILOT_MAX_DIAGNOSE_ITERS", "5"))
CONFIDENCE_THRESHOLD = float(os.getenv("OPSPILOT_CONFIDENCE_THRESHOLD", "0.75"))
MAX_TOOL_CALLS = int(os.getenv("OPSPILOT_MAX_TOOL_CALLS", "20"))


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
ENVIRONMENT = os.getenv("OPSPILOT_ENV", "local")  # local | dev | prod
LANGSMITH_ENABLED = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"
