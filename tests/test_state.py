"""State contract tests — the content-hash evidence reducer (no ML stack required).

The reducer is the fix for the observed failure mode: a re-entered diagnose loop appended the
same evidence reference on every pass (5x duplication) under a `list + operator.add` channel.
Keyed-by-content-hash with first-seen-wins makes re-entry idempotent while keeping genuinely
distinct (including contradictory) observations.
"""

from __future__ import annotations

from opspilot.state import EvidenceItem, InvestigationState, evidence_hash, merge_evidence


def _ev(source: str, ref: str, content: str = "") -> EvidenceItem:
    return EvidenceItem.make(source, ref, content)


def test_identical_evidence_hashes_equal():
    assert evidence_hash("logs", "logs:x:1", "boom") == evidence_hash("logs", "logs:x:1", "boom")
    assert _ev("logs", "logs:x:1", "b").content_hash == _ev("logs", "logs:x:1", "b").content_hash


def test_merge_dedups_identical_evidence():
    a, dup = _ev("logs", "logs:x:1", "boom"), _ev("logs", "logs:x:1", "boom")
    merged = merge_evidence({a.content_hash: a}, {dup.content_hash: dup})
    assert len(merged) == 1


def test_merge_keeps_contradictory_observations():
    # same ref, different content -> distinct hashes -> both survive (never silently collapsed)
    up, down = _ev("metrics", "metrics:s:err@t", "0%"), _ev("metrics", "metrics:s:err@t", "40%")
    assert up.content_hash != down.content_hash
    merged = merge_evidence({up.content_hash: up}, {down.content_hash: down})
    assert len(merged) == 2


def test_reentry_does_not_duplicate_evidence():
    """The regression guard: applying the same diagnose output five times yields one item,
    not five (the pre-migration `list + add` behavior)."""
    item = _ev("deploys", "deploys:checkout-api:dep-1", "deploy preceded onset")
    acc: dict[str, EvidenceItem] = {}
    for _ in range(5):
        acc = merge_evidence(acc, {item.content_hash: item})
    assert len(acc) == 1
    state = InvestigationState(evidence_by_id=acc)
    refs = state.evidence_refs()
    assert refs == ["deploys:checkout-api:dep-1"]
    assert len(refs) == len(set(refs))  # unique refs == items


def test_first_seen_wins_on_key_collision():
    first = _ev("logs", "logs:x:1", "same")
    later = _ev("logs", "logs:x:1", "same")
    merged = merge_evidence({first.content_hash: first}, {later.content_hash: later})
    assert merged[first.content_hash] is first
