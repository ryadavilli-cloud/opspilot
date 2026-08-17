"""The chat-model contract: one shape, whichever implementation answers it.

A call names the task it serves and carries its messages, and nothing else. There is one live
implementation, one fake, and cassette replay; a task label plus messages is all any of them needs,
so the contract carries no provider knobs, no sampling controls, and no model selection.

The result carries what an investigation has to be able to say afterwards about a call it made:
which task it served, which deployment answered, how long it took, and what it cost in tokens.
Those are recorded for every call rather than sampled, because a run that cannot account for its
model calls cannot be audited, and reconstructing them later from a provider bill is not an audit.
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
    """A completion and the provenance needed to account for the call that produced it.

    `prompt_version` is stamped by the caller from the prompt registry, and is empty when the
    prompt did not come from it.
    """

    text: str
    task: str
    deployment: str
    prompt_version: str = ""
    finish_reason: str = ""
    latency_ms: float = 0.0
    usage: dict[str, int] = field(default_factory=dict)


@runtime_checkable
class ChatModel(Protocol):
    """A callable chat model, named by the deployment that serves it."""

    deployment: str

    def complete(self, task: str, messages: list[ChatMessage]) -> ChatResult: ...
