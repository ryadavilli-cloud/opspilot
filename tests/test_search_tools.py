"""Contract tests for the retrieval tools (search_runbooks / search_past_incidents).

Verifies the envelope, metadata filters, the empty-not-error case, that the matched passage text
reaches the result (not just a pointer), and that every returned citation resolves to a real
knowledge document: the corpus preparation writes real KB docs and distractors indistinguishably
(`scripts/prepare_corpus.py`), so a citation may resolve to either. The retriever is built over a
fake Cosmos container and a deterministic embedder, with no live Azure dependency.
"""

from __future__ import annotations

from pathlib import Path

from fake_knowledge import knowledge_retriever
from fake_operational_records import corpus_records

from opspilot.evidence.admission import admit
from opspilot.evidence.operations import EvidenceSet
from opspilot.retrieval.retriever import PASSAGE_BUDGET, Passage
from opspilot.tools.contracts import Completeness, ExecutionOutcome
from opspilot.tools.service import ToolService

REPO_ROOT = Path(__file__).resolve().parents[1]
KB = REPO_ROOT / "data" / "kb"
DISTRACTORS = REPO_ROOT / "data" / "distractors"


def _kb_doc(ref: str) -> Path | None:
    """Resolve a citation to the KB or distractor file it names. KB docs are filed under
    `runbooks/architecture/postmortems`; distractors sit flat under one directory, both matched by
    the same frontmatter `id:` convention (`scripts/prepare_corpus.py::knowledge_documents`)."""
    ns, ident = ref.split(":", 1)
    if ns == "runbook":
        candidates = [KB / "runbooks" / f"{ident}.md", DISTRACTORS / f"{ident}.md"]
    elif ns == "architecture":
        candidates = [KB / "architecture" / f"{ident}.md", DISTRACTORS / f"{ident}.md"]
    elif ns == "postmortem":
        candidates = sorted((KB / "postmortems").glob(f"{ident}-*.md")) + sorted(
            DISTRACTORS.glob(f"{ident}-*.md")
        )
    else:
        return None
    return next((p for p in candidates if p.exists()), None)


def _svc() -> ToolService:
    return ToolService(corpus_records(), retriever_factory=knowledge_retriever)


def test_search_runbooks_returns_kb_docs_and_refs_resolve():
    r = _svc().search_runbooks(query="payment authorizations timing out", k=5)
    assert r.answered and r.results
    assert all(isinstance(p, Passage) for p in r.results)
    assert all(p.category in ("runbook", "architecture") for p in r.results)
    assert all(p.text for p in r.results)
    assert r.evidence_refs == [p.reference for p in r.results]
    for ref in r.evidence_refs:
        assert _kb_doc(ref) is not None, f"citation {ref} does not resolve to a doc"


def test_search_runbooks_surfaces_the_matching_runbook():
    r = _svc().search_runbooks(
        query="Cosmos connection pool exhausted causing payment-api authorization timeouts", k=5
    )
    assert r.answered
    assert any(p.reference == "runbook:payment-timeout" for p in r.results)


def test_search_runbooks_ranked_and_metadata_filtered():
    r = _svc().search_runbooks(query="throttling", k=5, service="cosmos-db")
    assert r.answered and r.results
    assert all("cosmos-db" in p.services for p in r.results)
    assert r.results == sorted(r.results, key=lambda p: -p.score)


def test_search_unknown_filter_is_empty_not_error():
    r = _svc().search_runbooks(query="anything", k=5, service="ghost-service")
    assert r.answered and r.completeness is Completeness.EMPTY
    assert r.results == [] and r.error is None


def test_search_invalid_input_is_error():
    assert _svc().search_runbooks(query="").outcome is ExecutionOutcome.REJECTED


def test_search_past_incidents_returns_postmortems():
    r = _svc().search_past_incidents(query="cosmos db 429 throttling on reads", k=3)
    assert r.answered and r.results
    assert all(p.category == "postmortem" for p in r.results)
    for ref in r.evidence_refs:
        assert _kb_doc(ref) is not None, f"citation {ref} does not resolve to a KB doc"


def test_search_tools_via_dispatcher():
    svc = _svc()
    assert svc.call("search_runbooks", query="deployment rollback").answered
    assert svc.call("search_past_incidents", query="service bus backlog").answered


def test_search_reports_unavailable_when_the_source_cannot_be_reached():
    svc = ToolService(
        corpus_records(), retriever_factory=lambda: knowledge_retriever(unreachable=True)
    )
    r = svc.search_runbooks(query="payment timeout", k=3)
    assert r.outcome is ExecutionOutcome.UNAVAILABLE
    assert r.completeness is Completeness.NOT_APPLICABLE
    assert r.results == []


# --- what retrieval is, once admission sees it --------------------------------------------------
def test_a_retrieval_that_cannot_execute_yields_a_limitation_and_no_passage():
    """A retrieval that did not answer leaves its question open, exactly like any other capability
    that did not answer. Passing silently would let an investigation read as though the knowledge
    had been consulted and found wanting."""
    svc = ToolService(
        corpus_records(), retriever_factory=lambda: knowledge_retriever(unreachable=True)
    )
    evidence = EvidenceSet(investigation_id="inv-1")

    admitted = admit(
        svc.search_runbooks(query="payment timeout"),
        evidence=evidence,
        question="does a runbook describe this failure",
    )

    assert admitted == [] and evidence.observations == []
    limitation = evidence.limitations[0]
    assert limitation.question == "does a runbook describe this failure"
    assert limitation.capability == "search_runbooks"
    assert [op.capability for op in evidence.operations] == ["search_runbooks"]


def test_a_successful_retrieval_produces_knowledge_rather_than_operational_evidence():
    """Passages join the knowledge set. A document cannot observe the running system, so nothing
    retrieval returns may become an observation about the current incident."""
    evidence = EvidenceSet(investigation_id="inv-1")
    result = _svc().search_runbooks(query="payment authorizations timing out")
    assert result.answered and result.results

    admitted = admit(result, evidence=evidence, question="does a runbook describe this failure")

    assert admitted == [] and evidence.observations == []
    assert evidence.limitations == []
    assert [op.outcome for op in evidence.operations] == [ExecutionOutcome.SUCCEEDED]


def test_the_passage_budget_is_not_a_number_a_caller_may_raise():
    """Expressible is the point: a request above the budget has no valid form rather than being
    accepted and quietly clipped."""
    over = _svc().search_runbooks(query="payment timeout", k=PASSAGE_BUDGET + 1)
    assert over.outcome is ExecutionOutcome.REJECTED
    assert len(_svc().search_runbooks(query="payment timeout").results) <= PASSAGE_BUDGET
