"""The offline judge's adapter: one Claude deployment in a Microsoft Foundry resource.

One purpose: judge messages in, `ChatResult` out. The judge scores briefs the runtime model
produced, and a judge sharing that model correlates its blind spots with the system's, so this
adapter exists to reach a deliberately different model family. It lives beside the Azure adapter
because the factory must be able to construct it, and it is deliberately not selectable by
configuration: `OPSPILOT_LLM_PROVIDER` may never name it, so no setting can route the
investigation graph onto the judge's model.

Deliberately absent: provider discovery, fallback, retries, routing, tools, streaming, generic
Anthropic support, and model-family selection. If the judge model changes later, this adapter
changes then.

The measurement configuration is fixed in code and reported on the adapter, because both halves
matter: fixed, so a report is comparable with the ones before it, and reported, so an edit here
is visible in every report it produced rather than silently breaking the history. Two provider
facts constrain it. `max_tokens` is a hard limit on total output, thinking plus response text, so
it is sized for both or a verdict truncates. And this model rejects `temperature`, `top_p`, and
`top_k` at non-default values and carries no manual thinking budget, so effort is the only lever.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from opspilot.llm.base import ChatMessage, ChatResult

# The judge's fixed measurement configuration. `THINKING` and `EFFORT` are what the request
# sends; the evaluation report records them beside the deployment, so a later edit from `medium`
# is a visible break in comparability rather than a silent one.
THINKING = "adaptive"
EFFORT = "medium"
# Total output the model may produce, thinking and response text together. The verdict itself is
# a small JSON object; the headroom is for the thinking that precedes it.
MAX_TOKENS = 16000


class ClaudeFoundryChatModel:
    """One live adapter to the Foundry Anthropic endpoint. Keyless, like every other path.

    The SDK is imported lazily on first call, exactly as the Azure adapter imports its own, so
    constructing the model touches no network and needs no optional dependency.
    """

    # Foundry serves the deployment from a Cognitive Services account, so the Entra token
    # audience is the same one every other model call in this system authenticates against.
    _TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"

    def __init__(self, deployment: str, *, endpoint: str | None) -> None:
        self.deployment = deployment
        self.thinking = THINKING
        self.effort = EFFORT
        self.max_tokens = MAX_TOKENS
        self._endpoint = endpoint
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            from anthropic import AnthropicFoundry  # lazy: optional `llm` dependency group
            from azure.identity import (  # lazy: optional `llm` dependency group
                DefaultAzureCredential,
                get_bearer_token_provider,
            )

            token_provider = get_bearer_token_provider(DefaultAzureCredential(), self._TOKEN_SCOPE)
            self._client = AnthropicFoundry(
                base_url=self._endpoint or "",
                azure_ad_token_provider=token_provider,
            )
        return self._client

    def complete(
        self, task: str, messages: list[ChatMessage], deadline_s: float | None = None
    ) -> ChatResult:
        from opspilot.llm.base import ChatResult

        # The Messages API takes the system instruction as its own parameter rather than as a
        # turn, so the mapping is by role: system content becomes `system`, everything else
        # stays a message in order.
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        turns = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]

        request: dict[str, Any] = {
            "model": self.deployment,
            "max_tokens": self.max_tokens,
            "messages": turns,
            "thinking": {"type": self.thinking},
            "output_config": {"effort": self.effort},
        }
        if system:
            request["system"] = system
        if deadline_s is not None:
            request["timeout"] = max(0.0, deadline_s)

        client = self._ensure_client()
        started = time.perf_counter()
        response = client.messages.create(**request)
        latency_ms = (time.perf_counter() - started) * 1000

        # Thinking blocks are the model's own working and are not the answer; the text blocks
        # are, and the existing verdict parser reads them exactly as it reads any other model's.
        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )
        usage = getattr(response, "usage", None)
        return ChatResult(
            text=text,
            task=task,
            deployment=self.deployment,
            finish_reason=str(response.stop_reason or ""),
            latency_ms=latency_ms,
            usage=(
                {
                    "prompt_tokens": usage.input_tokens,
                    "completion_tokens": usage.output_tokens,
                }
                if usage
                else {}
            ),
        )
