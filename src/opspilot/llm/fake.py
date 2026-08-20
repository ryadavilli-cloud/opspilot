"""A deterministic fake chat model: canned responses, no network, no dependency.

The offline stand-in for the seam. Give it either a list of responses, returned in order with the
last repeating once exhausted, or a callable mapping the messages to a response.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from opspilot.llm.base import ChatMessage, ChatResult


class FakeChatModel:
    deployment = "fake"

    def __init__(self, responses: Sequence[str] | Callable[[list[ChatMessage]], str]) -> None:
        self._responses = responses
        self._index = 0

    def complete(
        self, task: str, messages: list[ChatMessage], deadline_s: float | None = None
    ) -> ChatResult:
        if callable(self._responses):
            text = self._responses(messages)
        else:
            if not self._responses:
                raise ValueError("FakeChatModel has no responses")
            text = self._responses[min(self._index, len(self._responses) - 1)]
            self._index += 1
        return ChatResult(text=text, task=task, deployment=self.deployment)
