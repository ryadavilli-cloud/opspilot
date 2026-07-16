"""2d gate: every retrieval target the answer key names resolves to a well-formed KB doc.

This is the doc-integrity proof for the knowledge base — every `expected_retrieval` and every
historical `expected_match` (postmortem) points at a real file with matching id + source metadata,
and every historical incident has a postmortem (so Demo 2 / the fast path can match). The full
cross-corpus closure (evidence↔telemetry↔KB↔postmortems, all together) is Phase 2e.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
KB = REPO_ROOT / "data" / "kb"


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


build_goldens = _load("build_goldens", "data/answer_key/build_goldens.py")
SCENARIOS = build_goldens.load_scenarios()

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
