"""Provider-agnostic chat-model contract.

One OpenAI-compatible interface fronts every provider OpsPilot uses — qwen3:8b via Ollama,
gpt-4o-mini via OpenAI, Claude via Azure Foundry — so the diagnosis core never imports a vendor
SDK. The `replay` model (see `cassette.py`) satisfies the same contract from recorded responses and
pulls in no heavy dependency, so LLM wiring tests run deterministically in the lean CI lane.

Contracts-first (guideline §4): this is frozen before the LLM planner plugs in at 4b. `ChatResult`
carries `model_id` + `prompt_version` so every model call is attributable in the audit trail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ChatMessage:
    """One turn in a chat exchange. `role` is system | user | assistant | tool."""

    role: str
    content: str


@dataclass(frozen=True)
class ChatResult:
    """A model completion plus the provenance needed to audit it.

    `prompt_version` is stamped by the caller from the prompt registry (empty when the prompt did
    not come from the registry); `usage` holds token counts when the provider reports them.
    """

    text: str
    model_id: str
    prompt_version: str = ""
    finish_reason: str = ""
    usage: dict[str, int] = field(default_factory=dict)


@runtime_checkable
class ChatModel(Protocol):
    """A callable chat model. `temperature` defaults to 0.0 — eval runs must be reproducible."""

    model_id: str

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.0,
    ) -> ChatResult: ...
