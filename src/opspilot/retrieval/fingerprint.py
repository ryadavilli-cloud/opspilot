"""The identity of the knowledge corpus a run retrieved from (D-012).

Retrieval behavior moves with the corpus, and it moves without anything else a record carries
moving with it: an added postmortem, an edited passage, or a re-embedding at another dimension all
change what a search returns while the model deployment and every prompt version stay exactly as
they were. Two records from either side of such a change look comparable and are not, so the
corpus gets an identity of its own and travels beside the deployment and the prompt versions.

What the value is computed over is what a retrieval can act on: whether a passage is a candidate,
how it ranks against the rest, and what reaches an agent when it comes back. The embedding vectors
themselves are not among it. A vector is a function of the passage text and the deployment that
produced it, both of which are hashed, so folding in thousands of floats would add no information
and would make the identity depend on how a float survives a round trip through the store.

Nothing that differs between two preparations of the same corpus contributes: no timestamp, no
generated id, no ordering, and no record of where a document came from. Preparing one corpus twice
produces one value, which is what makes an unchanged fingerprint evidence rather than coincidence.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

# The passage fields a retrieval reads. `category` decides which collection a passage belongs to,
# `text` is both what the lexical pass scores and what an agent is shown, `identifiers` decides
# promotion, `date` is the time metadata promotion may read, and `id`, `doc_id`, and `title` are
# how a returned passage names itself. `provenance` is deliberately absent: nothing in the query
# path may branch on whether a passage is a distractor, so it cannot change what a search returns.
_SCALARS = ("id", "category", "doc_id", "title", "text", "date")

# Set-valued fields, sorted here rather than trusted: whether a passage is a candidate for a
# service-narrowed search is a membership question, and two orderings of one membership are one
# corpus.
_SETS = ("services", "identifiers")


def embedding_identity(deployment: str, dimensions: int) -> str:
    """How an embedding names itself inside a corpus fingerprint.

    Formatted in one place because two sides depend on it agreeing: corpus preparation, which
    vectorizes the passages, and the runtime, which vectorizes the questions asked of them. Two
    spellings of one deployment would report a corpus change on every deployment that made none.

    The dimension is part of the name because this model family truncates to a requested size, so
    one deployment at two dimensions produces two vector spaces that cannot be compared.
    """
    return f"{deployment}:{dimensions}"


def _scalar(value: Any) -> str | None:
    """Absent stays absent. A passage carrying no date and one carrying an empty date are
    different corpora, and collapsing both to the empty string would hide the difference."""
    return None if value is None else str(value)


def _members(value: Any) -> list[str]:
    return sorted(str(item) for item in (value or ()))


def fingerprint(rows: Iterable[Mapping[str, Any]], *, embedding: str) -> str:
    """One value naming this corpus as retrieval sees it, prepared by this embedding.

    `rows` are prepared passages, in whatever order the store returned them; they are ordered here
    by their own ids so that the value follows the corpus rather than the query that read it.
    `embedding` names the deployment that vectorized the passages and the dimension it produced,
    because the same passages embedded by a different model are a different corpus to search even
    though every character of them is unchanged.
    """
    passages = sorted(
        (
            {
                **{field: _scalar(row.get(field)) for field in _SCALARS},
                **{field: _members(row.get(field)) for field in _SETS},
            }
            for row in rows
        ),
        key=lambda passage: passage["id"] or "",
    )
    payload = json.dumps(
        {"embedding": embedding, "passages": passages},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
