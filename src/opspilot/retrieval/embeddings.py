"""Query-time embedding through the Azure OpenAI embedding deployment (D-003).

Corpus preparation embeds every passage at load time through this same deployment
(`scripts/prepare_corpus.py::embed_all`); this module embeds the query at read time, so the two
vectors are comparable. Keyless via managed identity, like every other Azure client here. No local
embedding model is loaded anywhere in the runtime image.
"""

from __future__ import annotations

from typing import Any, Protocol

from opspilot.data.operational_records import SourceUnavailable, unanswered_read


class QueryEmbedder(Protocol):
    def embed(self, text: str, *, deadline_s: float) -> list[float]: ...


class AzureQueryEmbedder:
    """Embeds a query string through an Azure OpenAI embedding deployment.

    The client is built lazily on first use, so importing this module, and constructing a
    `Retriever` with an injected embedder, never requires the optional `openai`/`azure-identity`
    packages or a credential.
    """

    def __init__(self, deployment: str, dimensions: int, endpoint: str, api_version: str) -> None:
        self._deployment = deployment
        self._dimensions = dimensions
        self._endpoint = endpoint
        self._api_version = api_version
        self._client: Any = None

    def _client_(self) -> Any:
        if self._client is None:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider
            from openai import AzureOpenAI

            token_provider = get_bearer_token_provider(
                DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
            )
            self._client = AzureOpenAI(
                azure_endpoint=self._endpoint,
                api_version=self._api_version,
                azure_ad_token_provider=token_provider,
            )
        return self._client

    def embed(self, text: str, *, deadline_s: float) -> list[float]:
        try:
            response = self._client_().embeddings.create(
                model=self._deployment, input=[text], timeout=deadline_s
            )
        except Exception as exc:  # noqa: BLE001 - the deployment did not answer
            raise unanswered_read(exc) from exc
        vector = list(response.data[0].embedding)
        if len(vector) != self._dimensions:
            raise SourceUnavailable("EmbeddingDimensionMismatch")
        return vector


_default: AzureQueryEmbedder | None = None


def default_query_embedder() -> AzureQueryEmbedder:
    """The process-wide query embedder (lazy, built once), over the deployed embedding model."""
    global _default
    if _default is None:
        from opspilot import config

        _default = AzureQueryEmbedder(
            config.EMBEDDING_DEPLOYMENT,
            config.EMBEDDING_DIMENSIONS,
            config.AZURE_OPENAI_ENDPOINT,
            config.AZURE_OPENAI_API_VERSION,
        )
    return _default
