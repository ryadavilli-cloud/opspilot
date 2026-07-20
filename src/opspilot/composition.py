"""Composition root for the diagnosis implementation — the one place that decides whether the
deployed app runs the deterministic floor or the single-agent LLM (planner + triager).

`build_diagnosis()` reads `OPSPILOT_IMPLEMENTATION`, and for `single_agent` builds ONE shared
`ChatModel` wrapped by an `LLMPlanner` and an `LLMTriager` (one model per process, reused across
investigations). The deterministic floor is an EXPLICIT fallback, never silent: if single_agent is
requested but its model can't be built — the optional `llm` deps are absent, the provider is
misconfigured, or the Azure endpoint is unset — we fall back to deterministic AND record why, so
`/version` and each investigation's `runtime` report the effective implementation and the reason.
"""

from __future__ import annotations

import importlib.util
import logging
from dataclasses import dataclass
from typing import Any

from opspilot import config

_log = logging.getLogger("opspilot.composition")


@dataclass(frozen=True)
class DiagnosisComposition:
    """The diagnosis pair the composition root injects, plus what it resolved to and why."""

    implementation: str          # effective implementation that actually runs
    requested: str               # what OPSPILOT_IMPLEMENTATION asked for
    planner: Any
    triager: Any
    provider: str | None = None
    model_id: str | None = None
    fallback_reason: str | None = None  # set only when a requested single_agent fell back


def _single_agent_blocker() -> str | None:
    """A cheap, no-network reason single_agent cannot run, or None if it can be built.

    Deliberately does not touch the network (no model preflight — that would cost a call on every
    cold start): it only catches configuration/packaging problems. A reachable-but-misauthorized
    endpoint still surfaces at call time as a failed investigation, never a silent success.
    """
    if importlib.util.find_spec("openai") is None:
        return "optional 'llm' dependency group is not installed (openai SDK missing)"
    provider = config.LLM_PROVIDER.lower()
    if provider not in ("ollama", "openai", "azure"):
        return f"provider {provider!r} cannot back single_agent (need ollama|openai|azure)"
    if provider == "azure":
        if not config.AZURE_OPENAI_ENDPOINT:
            return "provider=azure but AZURE_OPENAI_ENDPOINT is not set"
        if not config.AZURE_OPENAI_API_KEY and importlib.util.find_spec("azure.identity") is None:
            return "provider=azure keyless but the azure-identity package is not installed"
    return None


def _deterministic(requested: str, *, fallback_reason: str | None = None) -> DiagnosisComposition:
    from opspilot.diagnosis.planner import build_planner
    from opspilot.triage import build_triager

    return DiagnosisComposition(
        implementation="deterministic",
        requested=requested,
        planner=build_planner("deterministic"),
        triager=build_triager("deterministic"),
        fallback_reason=fallback_reason,
    )


def build_diagnosis(implementation: str | None = None) -> DiagnosisComposition:
    """Build the process-wide diagnosis pair for `implementation` (default: config)."""
    requested = (implementation or config.IMPLEMENTATION).lower()
    if requested != "single_agent":
        return _deterministic(requested)

    blocker = _single_agent_blocker()
    if blocker is not None:
        _log.warning("single_agent unavailable (%s); using deterministic floor", blocker)
        return _deterministic(requested, fallback_reason=blocker)

    try:
        from opspilot.diagnosis.planner import build_planner
        from opspilot.llm.client import build_chat_model
        from opspilot.triage import build_triager

        model = build_chat_model()  # provider/model resolved from config (azure in prod)
        planner = build_planner("single_agent", model=model)
        triager = build_triager("single_agent", model=model)
    except Exception as exc:  # noqa: BLE001 — any build failure -> explicit floor, never a broken app
        _log.warning("single_agent build failed (%s); using deterministic floor", exc)
        return _deterministic(requested, fallback_reason=f"{type(exc).__name__}: {exc}")

    return DiagnosisComposition(
        implementation="single_agent",
        requested=requested,
        planner=planner,
        triager=triager,
        provider=config.LLM_PROVIDER.lower(),
        model_id=getattr(model, "model_id", None),
    )
