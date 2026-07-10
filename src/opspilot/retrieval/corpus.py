"""Load and chunk the KB corpus (labeled docs) plus the distractor corpus (indexed, never labeled).

Chunking is section-level (by markdown header); each chunk carries its doc's id/kind/services and
is prefixed with the doc title for context. Retrieval ranks chunks and aggregates to doc ids, which
is what `golden_retrieval.json` labels.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
KB_DIR = _REPO_ROOT / "data" / "kb"
DISTRACTOR_DIR = _REPO_ROOT / "data" / "distractors"
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


def load_docs(include_distractors: bool = True) -> list[Doc]:
    docs: list[Doc] = []
    for sub in ("runbooks", "architecture", "postmortems"):
        for p in sorted((KB_DIR / sub).glob("*.md")):
            if (d := _parse(p, False)) is not None:
                docs.append(d)
    if include_distractors and DISTRACTOR_DIR.exists():
        for p in sorted(DISTRACTOR_DIR.glob("*.md")):
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
