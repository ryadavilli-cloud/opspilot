"""2e closure gate: the whole corpus must agree — the single "does it all still fit?" check.

Per-layer tests guard each artifact in isolation; this one is the end-to-end gate that fails if a
layer drifts from the answer key. It re-derives the four closure questions independently (it does
NOT import the generators' resolution logic) and adds cross-layer ties no single layer owns:

  1. every KB doc has an id + source metadata
  2. every scenario's expected evidence resolves to a telemetry row
  3. every expected retrieval target + postmortem resolves to a KB doc
  4. postmortems <-> historical incidents <-> incident records all line up
  5. alerts reference real entities; each storm's root_cause sits on the scenario's chain
  6. runbook cross-references inside postmortems resolve

If this passes, the Phase 4 retrieval and Phase 5 groundedness evals are scoring against a key that
holds together.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "data"
SYN = DATA / "synthetic"
KB = DATA / "kb"


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


build_goldens = _load("build_goldens", "data/answer_key/build_goldens.py")
TOPOLOGY = build_goldens.load_topology()
SCENARIOS = build_goldens.load_scenarios()

SERVICES = {s["id"] for s in TOPOLOGY["services"]}
INFRA = {i["id"] for i in TOPOLOGY["infra"]}
EXTERNALS = {e["id"] for e in TOPOLOGY["externals"]}
ENTITIES = SERVICES | INFRA | EXTERNALS
HISTORICAL = {s["id"] for s in SCENARIOS if s["type"] == "historical"}

# --- load every corpus artifact independently -------------------------------------------------
METRICS = json.loads((SYN / "metrics.json").read_text(encoding="utf-8"))["series"]
DEPLOYS = json.loads((SYN / "deployments.json").read_text(encoding="utf-8"))["deployments"]
EDGES = json.loads((SYN / "dependencies.json").read_text(encoding="utf-8"))["edges"]
LOGS = [json.loads(x) for x in (SYN / "logs.jsonl").read_text(encoding="utf-8").splitlines()]
ALERTS = json.loads((SYN / "alerts.json").read_text(encoding="utf-8"))["alerts"]
INCIDENTS = json.loads((SYN / "incidents.json").read_text(encoding="utf-8"))["incidents"]

METRIC_SAMPLES = {(s["service"], s["metric"], p["ts"]) for s in METRICS for p in s["samples"]}
LOG_BY_EVENT = {r["event_id"]: r for r in LOGS}
DEPLOY_BY_ID = {d["deploy_id"]: d for d in DEPLOYS}
EDGE_SET = {f"{e['from']}->{e['to']}" for e in EDGES}
INC_BY_SCEN = {i["incident_id"]: i for i in INCIDENTS}


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


def _frontmatter(path: Path) -> dict:
    _, fm, _ = path.read_text(encoding="utf-8").split("---", 2)
    return yaml.safe_load(fm)


# --- closure question 1 -----------------------------------------------------------------------
def test_1_every_kb_doc_has_id_and_source():
    docs = [p for d in ("runbooks", "architecture", "postmortems") for p in (KB / d).glob("*.md")]
    assert docs, "no KB docs found"
    for p in docs:
        fm = _frontmatter(p)
        assert fm.get("id"), f"{p}: missing id"
        assert fm.get("source"), f"{p}: missing source"


# --- closure question 2 -----------------------------------------------------------------------
def test_2_every_evidence_ref_resolves_to_telemetry():
    unresolved = []
    for s in SCENARIOS:
        for ref in s["expected_evidence"]:
            src, rest = ref.split(":", 1)
            if src == "metrics":
                svc, tail = rest.split(":", 1)
                metric, ts = tail.split("@", 1)
                ok = (svc, metric, ts) in METRIC_SAMPLES
            elif src == "logs":
                svc, eid = rest.rsplit(":", 1)
                ok = eid in LOG_BY_EVENT and LOG_BY_EVENT[eid]["service"] == svc
            elif src == "deploys":
                svc, did = rest.rsplit(":", 1)
                ok = did in DEPLOY_BY_ID and DEPLOY_BY_ID[did]["service"] == svc
            elif src == "deps":
                ok = rest in EDGE_SET
            else:
                ok = False
            if not ok:
                unresolved.append(ref)
    assert not unresolved, f"evidence refs with no telemetry: {unresolved}"


# --- closure question 3 -----------------------------------------------------------------------
def test_3_every_retrieval_target_resolves_to_kb():
    refs = {r for s in SCENARIOS for r in s["expected_retrieval"]}
    refs |= {s["expected_match"] for s in SCENARIOS if s.get("expected_match")}
    missing = [r for r in refs if _kb_doc(r) is None]
    assert not missing, f"retrieval targets with no KB doc: {missing}"


# --- closure question 4 -----------------------------------------------------------------------
def test_4_postmortems_incidents_and_history_align():
    for inc_id in HISTORICAL:
        assert _kb_doc(f"postmortem:{inc_id}") is not None, f"no postmortem for {inc_id}"
        rec = INC_BY_SCEN.get(inc_id)
        assert rec and rec["is_known_error"] and rec["state"] == "Closed", f"{inc_id} record wrong"
        assert rec.get("resolution"), f"{inc_id} closed without a resolution"
    # every incident record maps back to a scenario
    assert set(INC_BY_SCEN) == {s["id"] for s in SCENARIOS}


# --- closure question 5 (cross-layer tie) -----------------------------------------------------
def test_5_alerts_reference_real_entities_and_root_on_chain():
    for a in ALERTS:
        assert a["service"] in ENTITIES, f"alert on unknown entity {a['service']}"
    for s in SCENARIOS:
        storm = [a for a in ALERTS if a["incident_id"] == s["id"]]
        root = next(a for a in storm if a["role"] == "root_cause")
        assert root["service"] in s["impacted_chain"], f"{s['id']}: root_cause off the chain"


# --- closure question 6 (cross-layer tie) -----------------------------------------------------
def test_6_postmortem_runbook_crossrefs_resolve():
    ref_re = re.compile(r"runbook:[a-z0-9-]+")
    for p in (KB / "postmortems").glob("*.md"):
        for ref in set(ref_re.findall(p.read_text(encoding="utf-8"))):
            assert _kb_doc(ref) is not None, f"{p.name} references missing {ref}"


# --- closure question 7: recurrence-verification data model ------------------------------------
# The known-issue fast path trusts a candidate match only after checking the stored issue's
# required/disqualifying signals + affected versions. These fields must be authored in the answer
# key, mirrored verbatim in the postmortem frontmatter, and resolvable against real telemetry —
# otherwise verification could never succeed on a genuine recurrence.
METRIC_PAIRS = {(s["service"], s["metric"]) for s in METRICS}
LOG_LEVELS = {(r["service"], r["level"]) for r in LOGS}
VERIFICATION_FIELDS = ("required_signals", "disqualifying_signals", "affected_versions")


def _descriptor_resolves(descriptor: str) -> bool:
    """Class-level signal descriptor: metrics:<entity>:<metric> | logs:<service>:<level>."""
    parts = descriptor.split(":")
    if len(parts) != 3:
        return False
    kind, entity, tail = parts
    if kind == "metrics":
        return entity in ENTITIES and (entity, tail) in METRIC_PAIRS
    if kind == "logs":
        return entity in SERVICES and (entity, tail) in LOG_LEVELS
    return False


def _evidence_entities(scenario: dict) -> set[str]:
    ents = set()
    for ref in scenario["expected_evidence"]:
        src, rest = ref.split(":", 1)
        if src == "deps":
            ents.update(rest.split("->"))
        elif src == "metrics":
            ents.add(rest.split(":", 1)[0])
        else:
            ents.add(rest.rsplit(":", 1)[0])
    return ents


def test_7_verification_blocks_close_against_telemetry_and_postmortems():
    deploy_versions = {(d["service"], d["version"].split("@", 1)[1]) for d in DEPLOYS}
    for s in SCENARIOS:
        if s["type"] != "historical":
            continue
        verification = s.get("verification")
        assert verification, f"{s['id']}: historical scenario missing verification block"
        assert set(VERIFICATION_FIELDS) <= verification.keys(), f"{s['id']}: incomplete block"
        assert verification["required_signals"], f"{s['id']}: required_signals empty"
        assert verification["affected_versions"], f"{s['id']}: affected_versions empty"

        # the postmortem frontmatter mirrors the answer key verbatim (labels are truth)
        fm = _frontmatter(_kb_doc(f"postmortem:{s['id']}"))
        for field in VERIFICATION_FIELDS:
            assert fm.get(field) == verification[field], (
                f"{s['id']}: postmortem frontmatter {field} drifted from the answer key")

        # every descriptor resolves to a real telemetry signal class
        for descriptor in verification["required_signals"] + verification["disqualifying_signals"]:
            assert _descriptor_resolves(descriptor), f"{s['id']}: unresolvable {descriptor!r}"

        # required signals tie to the original incident (on its chain or in its evidence)
        tied = set(s["impacted_chain"]) | _evidence_entities(s)
        for descriptor in verification["required_signals"]:
            entity = descriptor.split(":")[1]
            assert entity in tied, f"{s['id']}: required signal {descriptor!r} off the incident"

        # affected versions are real deploys; a causal deploy's version must be listed
        for version in verification["affected_versions"]:
            svc, _, ver = version.partition("@")
            assert svc in SERVICES and ver, f"{s['id']}: bad affected_version {version!r}"
            assert (svc, ver) in deploy_versions, f"{s['id']}: {version!r} not in the deploy feed"
        causal = [r for r in s["expected_evidence"] if r.startswith("deploys:")]
        for ref in causal:
            deploy = DEPLOY_BY_ID[ref.rsplit(":", 1)[1]]
            assert deploy["version"] in verification["affected_versions"], (
                f"{s['id']}: causal deploy {deploy['version']} missing from affected_versions")
