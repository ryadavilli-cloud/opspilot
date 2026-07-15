"""Runtime asset loading — the corpus/KB must load from explicit paths, independent of cwd.

These guard the exact Docker failure mode: the image runs from `/app`, not the repo root, and the
data lives at an explicitly configured path rather than one inferred from the source-tree layout.
No ML stack required.
"""

from __future__ import annotations

import pytest

from opspilot.config import CORPUS_DIR, KB_DIR
from opspilot.data.repository import (
    CORPUS_FILES,
    Repository,
    default_repository,
    validate_corpus,
)
from opspilot.retrieval.corpus import load_docs


def test_validate_corpus_all_present_on_real_corpus():
    status = validate_corpus(CORPUS_DIR)
    assert status.ok and not status.missing
    assert set(status.present) == set(CORPUS_FILES)


def test_validate_corpus_reports_every_missing_file_together(tmp_path):
    status = validate_corpus(tmp_path)
    assert not status.ok
    assert set(status.missing) == set(CORPUS_FILES)  # one complete result, not one file at a time
    assert status.present == ()


def test_repository_loads_from_an_explicit_corpus_dir():
    repo = Repository(corpus_dir=CORPUS_DIR)
    assert repo.incident("inc-004") is not None


def test_missing_corpus_raises_one_error_listing_all_missing_files(tmp_path):
    with pytest.raises(FileNotFoundError) as exc:
        Repository(corpus_dir=tmp_path)
    message = str(exc.value)
    for name in CORPUS_FILES:
        assert name in message  # every missing file named in the single diagnostic


def test_explicit_kb_dir_loads_labeled_docs_only():
    docs = load_docs(KB_DIR)
    assert docs and all(not d.is_distractor for d in docs)


def test_repository_works_when_cwd_is_not_the_repo_root(tmp_path, monkeypatch):
    # The Docker scenario: run from a directory that is not the repo root. The default corpus
    # path is absolute (config-resolved), so a fresh repository still loads the corpus.
    monkeypatch.chdir(tmp_path)
    assert Repository().incident("inc-004") is not None
    assert default_repository().incident("inc-004") is not None
