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


def _returned(scenario_id: str) -> list[str]:
    """What a search on the incident as reported comes back with, in order and with repeats kept.

    Repeats are the thing worth being able to see. A set would hide the failure this contract
    exists to catch, where one write-up occupies the budget and the result looks like agreement
    rather than like one document counted five times.
    """
    from fake_knowledge import knowledge_retriever

    query = BY_ID[scenario_id]["alert"]["summary"]
    found = knowledge_retriever().search(query, k=5, collection="postmortem", deadline_s=5.0)
    return [p.reference for p in found]


def _precedents(scenario_id: str) -> set[str]:
    return set(_returned(scenario_id))


def test_the_incident_a_deployment_makes_obvious_is_reachable():
    """inc-004 answers the objection that the nearest write-up is good enough, so the write-up that
    makes the objection tempting has to be there to be reached."""
    assert "postmortem:inc-104" in _precedents("inc-004")


def test_the_cache_precedent_is_reachable_for_the_latency_incident():
    assert "postmortem:inc-105" in _precedents("inc-005")


def test_the_oversell_meets_its_two_precedents_through_two_different_questions():
    """One precedent per contributor, and no single write-up holding the pair, which is what leaves
    the combination for current evidence to establish.

    They are not both reachable from the same question, and that is the scenario rather than a
    defect in it. The reported symptom is a reservation conflict, which reaches the backlog
    history; nothing in it mentions staleness, so the cache history is reached only once evidence
    has given the investigation a reason to ask about staleness. A history that answered both
    halves to the opening question would be handing over a combination the incident exists to make
    someone assemble.
    """
    from fake_knowledge import knowledge_retriever

    assert "postmortem:inc-107" in _precedents("inc-006")

    informed = knowledge_retriever().search(
        "stale cached availability after a deploy dropped cache invalidation",
        k=5,
        collection="postmortem",
        deadline_s=5.0,
    )
    assert "postmortem:inc-106" in {p.reference for p in informed}


def test_the_recurrence_and_the_near_match_are_both_reachable():
    """Recognizing the recurrence is a discrimination, not the only option on offer."""
    found = _precedents("inc-007")
    assert "postmortem:inc-003" in found
    assert "postmortem:inc-108" in found


def test_a_search_of_history_spends_its_budget_on_distinct_incidents():
    """The contract the corpus was enlarged for: what comes back is several precedents to weigh.

    A budget spent on one write-up is one candidate counted repeatedly, which reads as agreement
    and is not. This is the assertion that fails if a past incident ever stops being one retrieval
    unit, so it is written against what was returned rather than against the set of it: collapsing
    to a set first would let five views of one incident pass as one distinct precedent.
    """
    for scenario_id in ("inc-004", "inc-005", "inc-006", "inc-007"):
        returned = _returned(scenario_id)
        assert len(returned) == len(set(returned)), f"{scenario_id} returned a write-up twice"
        assert len(returned) > 1, f"{scenario_id} met only one precedent"


def test_every_current_incident_meets_the_history_its_expectation_names():
    """The precedents a scenario is authored to be able to reach, checked through the real
    algorithm rather than trusted because they were written down.

    Reachability, not position. The embedder standing in here is 32 hashed dimensions against the
    deployed 1536, so what it orders is lexical rank wearing a hybrid costume; where a precedent
    lands is a claim only the real index can support. A precedent the opening report gives no
    reason to ask for is reached by the question that would follow the evidence, which is the
    oversell's second half and is asserted where that sequence is described.
    """
    reachable = {
        "inc-004": {"postmortem:inc-104", "postmortem:inc-109"},
        "inc-005": {"postmortem:inc-105"},
        "inc-006": {"postmortem:inc-107"},
        "inc-007": {"postmortem:inc-003", "postmortem:inc-108"},
    }
    for scenario_id, expected in reachable.items():
        missing = expected - _precedents(scenario_id)
        assert not missing, f"{scenario_id}: authored but not reachable: {sorted(missing)}"


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
