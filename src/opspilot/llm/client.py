"""Chat-model factory — selects a provider from config/env and returns a `ChatModel`.

Providers:
  - ``ollama`` / ``openai`` — an OpenAI-compatible HTTP client (the ``openai`` SDK, imported
    lazily). Ollama serves the OpenAI chat API at ``/v1``; OpenAI and Azure Foundry are the same
    shape with a real key. One client, three providers, differing only in base_url, api_key, model.
  - ``replay`` — recorded-cassette playback (no network, no ``openai`` dependency) for the
    deterministic LLM wiring tests that gate CI.

Unknown provider -> ``ValueError``, mirroring the retrieval factory: fail loud rather than silently
fall back to a different model than the caller asked for. Nothing heavy imports at module load.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from opspilot import config

if TYPE_CHECKING:
    from opspilot.llm.base import ChatMessage, ChatModel, ChatResult

_KNOWN = ("ollama", "openai", "replay")


class OpenAICompatModel:
    """A `ChatModel` over any OpenAI-compatible endpoint. The `openai` SDK is imported lazily on
    first call, so constructing the model (and importing this module) needs no optional dependency.
    """

    def __init__(self, model_id: str, *, base_url: str | None, api_key: str) -> None:
        self.model_id = model_id
        self._base_url = base_url or None
        self._api_key = api_key
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI  # lazy: optional `llm` dependency group

            self._client = OpenAI(base_url=self._base_url, api_key=self._api_key)
        return self._client

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.0,
    ) -> ChatResult:
        from opspilot.llm.base import ChatResult

        resp = self._ensure_client().chat.completions.create(
            model=self.model_id,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=temperature,
        )
        choice = resp.choices[0]
        usage = getattr(resp, "usage", None)
        return ChatResult(
            text=choice.message.content or "",
            model_id=self.model_id,
            finish_reason=choice.finish_reason or "",
            usage=(
                {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                }
                if usage
                else {}
            ),
        )


def _endpoint(provider: str) -> tuple[str | None, str]:
    """Resolve (base_url, api_key) for a live provider from config/env."""
    if provider == "ollama":
        # Ollama ignores the key but the OpenAI SDK requires a non-empty one.
        base_url = config.LLM_BASE_URL or config.OLLAMA_BASE_URL
        return base_url, (config.LLM_API_KEY or "ollama")
    # openai / Foundry: empty base_url -> the SDK's default OpenAI endpoint.
    return (config.LLM_BASE_URL or None), config.LLM_API_KEY


def build_chat_model(
    provider: str | None = None,
    *,
    model: str | None = None,
    cassette: str | None = None,
) -> ChatModel:
    """Build a `ChatModel` for `provider` (default: `config.LLM_PROVIDER`).

    `model` overrides `config.LLM_MODEL`; `cassette` is the recording path for the replay provider.
    Unknown provider -> ValueError.
    """
    provider = (provider or config.LLM_PROVIDER).lower()

    if provider == "replay":
        if not cassette:
            raise ValueError("the 'replay' provider requires a cassette path")
        from opspilot.llm.cassette import ReplayChatModel

        return ReplayChatModel(cassette)

    if provider in ("ollama", "openai"):
        base_url, api_key = _endpoint(provider)
        return OpenAICompatModel(model or config.LLM_MODEL, base_url=base_url, api_key=api_key)

    raise ValueError(f"unknown LLM provider {provider!r}; known: {', '.join(_KNOWN)}")
