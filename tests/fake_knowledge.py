"""A stand-in for the `knowledge` container, and a deterministic query embedder for tests.

Mirrors `fake_operational_records.py`: the container object is injected into `KnowledgeRecords`, so
a test holds this and the deployed path holds a real Cosmos container. `FakeKnowledgeContainer`
answers by interpreting the parameters, not by parsing the query text: a `@qv` parameter means
"rank by similarity to the document's own `embedding` field," the fake's stand-in for Cosmos's
`VectorDistance()`; `@categories`/`@services` mean membership/intersection filters. That is the
shape every authored knowledge query takes.

`FakeQueryEmbedder` never calls Azure OpenAI: it derives a small deterministic vector from a text's
tokens (a hashing trick, not a real embedding), so two similar texts land closer together and the
same text always embeds to the same vector, in-process and across runs. It is comparable only
against other vectors from the same embedder, never against a real Azure OpenAI vector.
"""

from __future__ import annotations

import functools
import hashlib
import importlib.util
import math
import sys
from pathlib import Path
from typing import Any

from opspilot.data.knowledge_records import KnowledgeRecords
from opspilot.retrieval.base import tokenize
from opspilot.retrieval.retriever import Retriever

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PROJECTED_FIELDS = (
    "id",
    "chunk_id",
    "category",
    "doc_id",
    "title",
    "text",
    "services",
    "identifiers",
    "date",
    "provenance",
)


@functools.cache
def _preparation():
    """`scripts/prepare_corpus.py`, imported by path the way `fake_operational_records.py` already
    imports it: the corpus files are shaped into container documents by preparation and by nothing
    else, so a fixture that reshaped them itself would be asserting against a second, unowned
    shaping."""
    spec = importlib.util.spec_from_file_location(
        "opspilot_prepare_corpus", _REPO_ROOT / "scripts" / "prepare_corpus.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ContainerUnreachable(RuntimeError):
    """What a container raises when it cannot answer at all."""


class FakeQueryEmbedder:
    """A deterministic stand-in for `AzureQueryEmbedder`. No network call, no Azure credential."""

    def __init__(self, dimensions: int = 32) -> None:
        self.dimensions = dimensions
        self.calls: list[str] = []

    def embed(self, text: str, *, deadline_s: float) -> list[float]:
        self.calls.append(text)
        return hash_embed(text, self.dimensions)


def hash_embed(text: str, dimensions: int) -> list[float]:
    """A cheap, deterministic bag-of-tokens embedding: each token votes for a hash-derived bucket,
    and the result is L2-normalized. Two texts sharing tokens land closer together; that is the only
    property these tests need from an embedding."""
    vector = [0.0] * dimensions
    for token in tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        vector[bucket] += 1.0
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector] if norm else vector


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


class FakeKnowledgeContainer:
    """Enough of a Cosmos container to answer the authored knowledge queries.

    `unreachable=True` makes every read raise, which is how "the source did not answer" is told
    apart from "the source answered with nothing".
    """

    def __init__(self, documents: list[dict[str, Any]], *, unreachable: bool = False) -> None:
        self.documents = documents
        self.unreachable = unreachable
        self.timeouts: list[float] = []
        self.queries: list[str] = []

    def query_items(
        self,
        query: str,
        parameters: list[dict[str, Any]] | None = None,
        enable_cross_partition_query: bool = False,
        timeout: float | None = None,
        **_: Any,
    ) -> list[Any]:
        self.queries.append(query)
        self.timeouts.append(timeout)  # type: ignore[arg-type]
        if self.unreachable:
            raise ContainerUnreachable("the container refused the connection")

        by_name = {p["name"]: p["value"] for p in (parameters or [])}
        matched = [doc for doc in self.documents if self._matches(doc, by_name)]

        if "COUNT(1)" in query:
            return [len(matched)]

        if "@qv" in by_name:
            qv = by_name["@qv"]
            ranked = sorted(matched, key=lambda doc: -_cosine(doc["embedding"], qv))
            return [self._project(doc, _cosine(doc["embedding"], qv)) for doc in ranked]

        return list(matched)

    def _matches(self, document: dict[str, Any], by_name: dict[str, Any]) -> bool:
        if "@categories" in by_name and document.get("category") not in by_name["@categories"]:
            return False
        if "@category" in by_name and document.get("category") != by_name["@category"]:
            return False
        if "@services" in by_name:
            wanted = set(by_name["@services"])
            if not wanted & set(document.get("services") or ()):
                return False
        return True

    @staticmethod
    def _project(document: dict[str, Any], score: float) -> dict[str, Any]:
        row = {field: document.get(field) for field in _PROJECTED_FIELDS}
        row["score"] = score
        return row


@functools.cache
def _knowledge_documents() -> tuple[dict[str, Any], ...]:
    """Every knowledge passage, shaped exactly as preparation writes it, plus a fake embedding per
    passage (preparation itself never embeds without a live Azure OpenAI deployment)."""
    docs = _preparation().knowledge_documents()
    for doc in docs:
        doc["embedding"] = hash_embed(doc["text"], 32)
    return tuple(docs)


def knowledge_documents() -> list[dict[str, Any]]:
    """The real authored KB corpus, container-shaped. Fixture truth for tests asserting against
    real runbooks, architecture docs, and postmortems."""
    return list(_knowledge_documents())


def knowledge_container(**kwargs: Any) -> FakeKnowledgeContainer:
    return FakeKnowledgeContainer(knowledge_documents(), **kwargs)


def knowledge_retriever(*, dimensions: int = 32, **kwargs: Any) -> Retriever:
    """A retriever over the whole authored KB corpus, container-shaped, with a deterministic
    embedder: the fixture most tests want."""
    return Retriever(KnowledgeRecords(knowledge_container(**kwargs)), FakeQueryEmbedder(dimensions))


def retriever_from(documents: list[dict[str, Any]], **kwargs: Any) -> Retriever:
    """A retriever over hand-built documents, for cases the authored corpus does not hold. Each
    document must already carry an `embedding` (see `hash_embed`)."""
    return Retriever(
        KnowledgeRecords(FakeKnowledgeContainer(documents, **kwargs)), FakeQueryEmbedder()
    )
