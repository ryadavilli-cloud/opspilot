"""Load and chunk the KB corpus (labeled docs) plus an optional distractor corpus.

Chunking is section-level (by markdown header); each chunk carries its doc's id/kind/services and
is prefixed with the doc title for context. Retrieval ranks chunks and aggregates to doc ids, which
is what `golden_retrieval.json` labels. Paths are passed in explicitly — there are no module-level
directory constants — so a runtime image points at `/app/data/kb` and never accidentally indexes
distractors (`include_distractors` defaults to False; distractors are an evaluation-only device).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

_HEADER = re.compile(r"^#{1,6}\s+")


@dataclass(frozen=True)
class Doc:
    doc_id: str
    kind: str
    title: str
    services: tuple[str, ...]
    text: str
    is_distractor: bool


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    kind: str
    services: tuple[str, ...]
    text: str


def _parse(path: Path, is_distractor: bool) -> Doc | None:
    raw = path.read_text(encoding="utf-8")
    if not raw.lstrip().startswith("---"):
        return None
    _, fm_text, body = raw.split("---", 2)
    fm = yaml.safe_load(fm_text) or {}
    if "id" not in fm:
        return None
    return Doc(
        doc_id=fm["id"],
        kind=fm.get("kind", ""),
        title=fm.get("title", ""),
        services=tuple(fm.get("services") or ()),
        text=body.strip(),
        is_distractor=is_distractor,
    )


def load_docs(
    kb_dir: Path | str,
    distractor_dir: Path | str | None = None,
    include_distractors: bool = False,
) -> list[Doc]:
    """Load labeled KB docs from `kb_dir`. Distractors are indexed only when explicitly enabled
    (evaluation) — production passes `include_distractors=False` and never mixes them in."""
    kb_dir = Path(kb_dir)
    docs: list[Doc] = []
    for sub in ("runbooks", "architecture", "postmortems"):
        for p in sorted((kb_dir / sub).glob("*.md")):
            if (d := _parse(p, False)) is not None:
                docs.append(d)
    if include_distractors and distractor_dir is not None and Path(distractor_dir).exists():
        for p in sorted(Path(distractor_dir).glob("*.md")):
            if (d := _parse(p, True)) is not None:
                docs.append(d)
    return docs


def chunk(doc: Doc) -> list[Chunk]:
    """Split a doc into section chunks (title-prefixed). Header-less docs become one chunk."""
    chunks: list[Chunk] = []
    current: list[str] = []
    idx = 0

    def flush() -> None:
        nonlocal idx
        body = "\n".join(current).strip()
        if body:
            text = f"{doc.title}\n{body}".strip()
            chunks.append(Chunk(f"{doc.doc_id}#{idx}", doc.doc_id, doc.kind, doc.services, text))
            idx += 1

    for line in doc.text.splitlines():
        if _HEADER.match(line) and current:
            flush()
            current = [line]
        else:
            current.append(line)
    flush()
    if not chunks:
        text = f"{doc.title}\n{doc.text}".strip()
        chunks.append(Chunk(f"{doc.doc_id}#0", doc.doc_id, doc.kind, doc.services, text))
    return chunks
