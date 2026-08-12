"""Runtime asset loading: the KB must load from an explicit path, independent of cwd.

This guards the exact Docker failure mode: the image runs from `/app`, not the repo root, and the
data lives at an explicitly configured path rather than one inferred from the source-tree layout.
No ML stack required.

The operational corpus is no longer among these assets. It is read from the `operational-records`
container, so there is no file for the image to ship and no path for it to resolve; the tests that
guarded that loading are retired with the file-backed repository. What remains here is the
knowledge base, which is still read from the image.
"""

from __future__ import annotations

from opspilot.config import KB_DIR
from opspilot.retrieval.corpus import load_docs


def test_explicit_kb_dir_loads_labeled_docs_only():
    docs = load_docs(KB_DIR)
    assert docs and all(not d.is_distractor for d in docs)
