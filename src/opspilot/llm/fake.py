"""A deterministic fake `ChatModel` — canned responses, no network, no dependency.

The offline stand-in for the model abstraction: drive the LLM diagnosis/triage nodes in tests and
demos without a live provider or a recorded cassette. Give it either a list of responses (returned
in order; the last repeats once exhausted) or a callable that maps the messages to a response.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from opspilot.llm.base import ChatMessage, ChatResult


class FakeChatModel:
    model_id = "fake"

    def __init__(self, responses: Sequence[str] | Callable[[list[ChatMessage]], str]) -> None:
        self._responses = responses
        self._index = 0

    def complete(self, messages: list[ChatMessage], *, temperature: float = 0.0) -> ChatResult:
        if callable(self._responses):
            text = self._responses(messages)
        else:
            if not self._responses:
                raise ValueError("FakeChatModel has no responses")
            text = self._responses[min(self._index, len(self._responses) - 1)]
            self._index += 1
        return ChatResult(text=text, model_id=self.model_id)
