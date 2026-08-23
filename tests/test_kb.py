"""2d gate: every retrieval target the answer key names resolves to a well-formed KB doc.

This is the doc-integrity proof for the knowledge base — every `expected_retrieval` and every
historical `expected_match` (postmortem) points at a real file with matching id + source metadata,
and every historical incident has a postmortem (so Demo 2 / the fast path can match). The full
cross-corpus closure (evidence↔telemetry↔KB↔postmortems, all together) is `test_closure.py`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import answer_key
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
KB = REPO_ROOT / "data" / "kb"


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SCENARIOS = answer_key.SCENARIOS

RETRIEVAL_REFS = sorted({r for s in SCENARIOS for r in s["expected_retrieval"]})
POSTMORTEM_REFS = sorted({s["expected_match"] for s in SCENARIOS if s.get("expected_match")})
HISTORICAL = {s["id"] for s in SCENARIOS if s["type"] == "historical"}


def _resolve(ref: str) -> Path | None:
    ns, ident = ref.split(":", 1)
    if ns == "runbook":
        p = KB / "runbooks" / f"{ident}.md"
    elif ns == "architecture":
        p = KB / "architecture" / f"{ident}.md"
    elif ns == "postmortem":
        matches = sorted((KB / "postmortems").glob(f"{ident}-*.md"))
        return matches[0] if matches else None
    else:
        return None
    return p if p.exists() else None


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.lstrip().startswith("---"), f"{path}: no YAML frontmatter"
    _, fm, _ = text.split("---", 2)
    return yaml.safe_load(fm)


def test_every_retrieval_and_postmortem_ref_resolves():
    unresolved = [ref for ref in RETRIEVAL_REFS + POSTMORTEM_REFS if _resolve(ref) is None]
    assert not unresolved, f"KB docs missing for: {unresolved}"


def test_docs_carry_matching_id_and_source_metadata():
    for ref in RETRIEVAL_REFS + POSTMORTEM_REFS:
        fm = _frontmatter(_resolve(ref))
        assert fm.get("id") == ref, f"{ref}: frontmatter id is {fm.get('id')!r}"
        assert fm.get("source"), f"{ref}: missing source metadata"
        assert fm.get("kind") in {"runbook", "architecture", "postmortem"}, f"{ref}: bad kind"


def test_postmortems_correspond_to_historical_incidents():
    for ref in POSTMORTEM_REFS:
        assert ref.split(":", 1)[1] in HISTORICAL, f"{ref} is not a historical incident"
    for inc in HISTORICAL:  # every historical incident must have a postmortem doc
        assert _resolve(f"postmortem:{inc}") is not None, f"no postmortem for {inc}"


def test_postmortems_carry_the_verification_data_model():
    """Every postmortem must expose the machine-checkable recurrence signature the known-issue
    fast path verifies against (cross-corpus resolution is closure question 7)."""
    for ref in POSTMORTEM_REFS:
        fm = _frontmatter(_resolve(ref))
        assert fm.get("required_signals"), f"{ref}: missing/empty required_signals"
        assert fm.get("affected_versions"), f"{ref}: missing/empty affected_versions"
        assert isinstance(fm.get("disqualifying_signals"), list), f"{ref}: bad disqualifying"


# --- the authored relationships actually surface -------------------------------------------------
# Authoring a precedent into the corpus is not the same as the retriever returning it. A larger
# history changes vector order, lexical order, fusion, promotion, and what survives the budget, so
# a scenario that depends on meeting a particular past incident has to be checked against the real
# algorithm rather than against the intention behind the document.
#
# What is asserted here is presence: the precedent is reachable within the budget for a question
# shaped like the incident. Position is deliberately not asserted. The embedder standing in for
# Azure here is 32 hashed dimensions against the deployed 1536, so its dense half discriminates
# too weakly to be evidence about semantic order; that claim belongs to the real index.
BY_ID = {s["id"]: s for s in SCENARIOS}


def _precedents(scenario_id: str) -> set[str]:
    from fake_knowledge import knowledge_retriever

    query = BY_ID[scenario_id]["alert"]["summary"]
    found = knowledge_retriever().search_incidents(query, k=5, deadline_s=5.0)
    return {p.reference for p in found}


def test_the_incident_a_deployment_makes_obvious_is_reachable():
    """inc-004 answers the objection that the nearest write-up is good enough, so the write-up that
    makes the objection tempting has to be there to be reached."""
    assert "postmortem:inc-104" in _precedents("inc-004")


def test_the_cache_precedent_is_reachable_for_the_latency_incident():
    assert "postmortem:inc-105" in _precedents("inc-005")


def test_both_halves_of_the_oversell_are_reachable_separately():
    """One precedent per contributor and no single write-up holding the pair, which is what makes
    the current evidence rather than the history establish the combination."""
    found = _precedents("inc-006")
    assert "postmortem:inc-107" in found
    assert "postmortem:inc-106" in found


def test_the_recurrence_and_the_near_match_are_both_reachable():
    """Recognizing the recurrence is a discrimination, not the only option on offer."""
    found = _precedents("inc-007")
    assert "postmortem:inc-003" in found
    assert "postmortem:inc-108" in found


def test_a_scenario_meets_more_than_one_candidate_precedent():
    """The corpus exists to make retrieval produce candidates to weigh. One result would be an
    answer handed over rather than a set to discriminate between."""
    for scenario_id in ("inc-004", "inc-005", "inc-006", "inc-007"):
        assert len(_precedents(scenario_id)) > 1, scenario_id


def test_the_precedent_the_shortcut_should_reach_is_named_and_resolves():
    """Only where the shortcut runs. Elsewhere there is nothing for it to be right or wrong
    about, so naming a precedent would assert something the scenario does not test."""
    named = {
        s["id"]: s["evaluation"]["nearest_history_should_select"]
        for s in SCENARIOS
        if "nearest_history_should_select" in s["evaluation"]
    }
    assert set(named) == {"inc-004", "inc-007"}
    assert named["inc-007"] == "postmortem:inc-003"
    for scenario_id, ref in named.items():
        assert _resolve(ref) is not None, f"{scenario_id}: {ref} resolves to no write-up"
        assert ref in _precedents(scenario_id), f"{scenario_id}: {ref} is not even reachable"


def test_guidance_stays_reachable_without_pinning_where_it_lands():
    """Runbook search answers with sections, and which section answers a question best is exactly
    the kind of thing a corpus edit may reasonably change. Reachability is the contract."""
    from fake_knowledge import knowledge_retriever

    hits = knowledge_retriever().search(
        "redis cache eviction and memory pressure",
        k=5,
        collection=("runbook", "architecture"),
        deadline_s=5.0,
    )
    assert "runbook:redis-cache-degradation" in {h.reference for h in hits}
