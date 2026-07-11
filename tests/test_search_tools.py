"""Contract tests for the retrieval tools (search_runbooks / search_past_incidents).

Skipped without the retrieval extras. Building the ToolService retriever embeds the KB once
(module fixture). Verifies the envelope, metadata filters, the empty-not-error case, and that
every returned citation resolves to a real KB document.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("sentence_transformers")
pytest.importorskip("rank_bm25")

from opspilot.tools.contracts import DocHit  # noqa: E402
from opspilot.tools.service import ToolService  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
KB = REPO_ROOT / "data" / "kb"


def _kb_doc(ref: str) -> Path | None:
    ns, ident = ref.split(":", 1)
    if ns == "runbook":
        p = KB / "runbooks" / f"{ident}.md"
    elif ns == "architecture":
        p = KB / "architecture" / f"{ident}.md"
    elif ns == "postmortem":
        found = sorted((KB / "postmortems").glob(f"{ident}-*.md"))
        return found[0] if found else None
    else:
        return None
    return p if p.exists() else None


@pytest.fixture(scope="module")
def svc() -> ToolService:
    return ToolService()


def test_search_runbooks_returns_kb_docs_and_refs_resolve(svc):
    r = svc.search_runbooks(query="payment authorizations timing out", k=5)
    assert r.status == "ok" and r.results
    assert all(isinstance(h, DocHit) for h in r.results)
    assert all(h.kind in ("runbook", "architecture") for h in r.results)
    assert r.evidence_refs == [h.doc_id for h in r.results]
    for ref in r.evidence_refs:
        assert _kb_doc(ref) is not None, f"citation {ref} does not resolve to a KB doc"


def test_search_runbooks_ranked_and_metadata_filtered(svc):
    r = svc.search_runbooks(query="throttling", k=5, service="cosmos-db")
    assert r.status == "ok" and r.results
    assert all("cosmos-db" in h.services for h in r.results)
    assert r.results == sorted(r.results, key=lambda h: -h.score)


def test_search_unknown_filter_is_empty_not_error(svc):
    r = svc.search_runbooks(query="anything", k=5, service="ghost-service")
    assert r.status == "ok" and r.results == [] and r.error is None


def test_search_invalid_input_is_error(svc):
    assert svc.search_runbooks(query="").status == "error"


def test_search_past_incidents_returns_postmortems(svc):
    r = svc.search_past_incidents(query="cosmos db 429 throttling on reads", k=3)
    assert r.status == "ok" and r.results
    assert all(h.kind == "postmortem" for h in r.results)
    for ref in r.evidence_refs:
        assert _kb_doc(ref) is not None, f"citation {ref} does not resolve to a KB doc"


def test_search_tools_via_dispatcher(svc):
    assert svc.call("search_runbooks", query="deployment rollback").status == "ok"
    assert svc.call("search_past_incidents", query="service bus backlog").status == "ok"
