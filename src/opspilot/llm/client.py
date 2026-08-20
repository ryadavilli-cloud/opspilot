"""The chat-model factory: one live adapter, or recorded replay.

There is one provider. Azure OpenAI serves every model task through one chat deployment, and the
factory's only other answer is cassette replay, which needs no network and no provider SDK so the
deterministic test lane never reaches a live service.

Authentication is keyless and has no alternative. The Azure OpenAI account has local authentication
disabled, so no key exists to configure, and an api-key branch beside this one would be a fallback
to a path that cannot work. `DefaultAzureCredential` resolves the Container App's managed identity
in production and a developer's `az login` locally, which is the same code path in both.

An unknown provider raises rather than falling back to something else, mirroring the retrieval
factory: silently answering with a different model than the caller asked for is how a run gets
certified against something it never ran on.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from opspilot import config

if TYPE_CHECKING:
    from opspilot.llm.base import ChatMessage, ChatModel, ChatResult

_KNOWN = ("azure", "replay")

# Reasoning models (gpt-5*, o1/o3/o4*) reject an explicit `temperature`, so the request carries
# `reasoning_effort` instead. Detected by deployment-name prefix, which is how the deployment is
# named after its model in this account.
_REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def _is_reasoning_model(deployment: str) -> bool:
    return deployment.startswith(_REASONING_PREFIXES)


class AzureChatModel:
    """The one live adapter. `deployment` is the Azure deployment name the request calls.

    The Azure SDK is imported lazily on first call, so importing this module needs no optional
    dependency and constructing the model touches no network.
    """

    _TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"

    def __init__(self, deployment: str, *, endpoint: str | None, api_version: str) -> None:
        self.deployment = deployment
        self._endpoint = endpoint
        self._api_version = api_version
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            from azure.identity import (  # lazy: optional `llm` dependency group
                DefaultAzureCredential,
                get_bearer_token_provider,
            )
            from openai import AzureOpenAI  # lazy: optional `llm` dependency group

            token_provider = get_bearer_token_provider(DefaultAzureCredential(), self._TOKEN_SCOPE)
            self._client = AzureOpenAI(
                azure_endpoint=self._endpoint or "",
                api_version=self._api_version,
                azure_ad_token_provider=token_provider,
            )
        return self._client

    def complete(
        self, task: str, messages: list[ChatMessage], deadline_s: float | None = None
    ) -> ChatResult:
        from opspilot.llm.base import ChatResult

        payload = [{"role": m.role, "content": m.content} for m in messages]
        client = self._ensure_client()
        started = time.perf_counter()
        # What the run has left, handed to the request itself. Effort bounds how much a reasoning
        # model thinks; only this bounds how long the caller waits, and without it a single call
        # could outlast the investigation that made it and go on spending after it had stopped.
        bound = {} if deadline_s is None else {"timeout": max(0.0, deadline_s)}
        if _is_reasoning_model(self.deployment):
            # Left unbounded, a reasoning model's hidden tokens make each call slow and expensive.
            # The configured effort keeps latency inside the request while staying thorough enough
            # to work through the whole evidence set.
            resp = client.chat.completions.create(
                model=self.deployment,
                messages=payload,
                reasoning_effort=config.REASONING_EFFORT,
                **bound,
            )
        else:
            resp = client.chat.completions.create(model=self.deployment, messages=payload, **bound)
        latency_ms = (time.perf_counter() - started) * 1000
        choice = resp.choices[0]
        usage = getattr(resp, "usage", None)
        return ChatResult(
            text=choice.message.content or "",
            task=task,
            deployment=self.deployment,
            finish_reason=choice.finish_reason or "",
            latency_ms=latency_ms,
            usage=(
                {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                }
                if usage
                else {}
            ),
        )


def build_chat_model(
    provider: str | None = None,
    *,
    deployment: str | None = None,
    cassette: str | None = None,
) -> ChatModel:
    """Build a `ChatModel` for `provider` (default: `config.LLM_PROVIDER`).

    `deployment` overrides `config.AZURE_OPENAI_DEPLOYMENT`; `cassette` is the recording path the
    replay provider reads. Unknown provider raises.
    """
    provider = (provider or config.LLM_PROVIDER).lower()

    if provider == "replay":
        if not cassette:
            raise ValueError("the 'replay' provider requires a cassette path")
        from opspilot.llm.cassette import ReplayChatModel

        return ReplayChatModel(cassette)

    if provider == "azure":
        return AzureChatModel(
            deployment or config.AZURE_OPENAI_DEPLOYMENT,
            endpoint=config.AZURE_OPENAI_ENDPOINT or None,
            api_version=config.AZURE_OPENAI_API_VERSION,
        )

    raise ValueError(f"unknown LLM provider {provider!r}; known: {', '.join(_KNOWN)}")


class TracedChatModel:
    """Wraps any `ChatModel` to emit one span per call from what the result already carries.

    Capture only: the span records the task, deployment, latency, and token usage the call
    reported, and nothing reads them back to enforce anything here.
    """

    def __init__(self, inner: ChatModel) -> None:
        self._inner = inner
        self.deployment = inner.deployment

    def complete(
        self, task: str, messages: list[ChatMessage], deadline_s: float | None = None
    ) -> ChatResult:
        from opspilot.obs.tracing import span

        with span("model.complete", attributes={"task": task}) as sp:
            result = self._inner.complete(task, messages)
            usage = result.usage or {}
            sp.attributes["model_deployment"] = result.deployment
            sp.attributes["latency_ms"] = result.latency_ms
            sp.attributes["tokens_in"] = usage.get("prompt_tokens", 0)
            sp.attributes["tokens_out"] = usage.get("completion_tokens", 0)
            sp.attributes["finish_reason"] = result.finish_reason
            return result
