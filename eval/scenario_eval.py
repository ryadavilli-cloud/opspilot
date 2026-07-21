"""Scenario evaluation of the connected slice: ingest -> triage -> retrieve/tools -> hypothesis.

Runs all six scenarios through the graph and scores a scorecard. The scorecard is stored as a
versioned baseline (eval/baselines/slice_baseline.json); the gate test fails on material
regression. `evaluate(implementation=...)` is deliberately generic so the same scoring can later
compare the deterministic, single-agent, and multi-agent implementations.

Run:  python eval/scenario_eval.py     # regenerates the baseline
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from opspilot.config import MAX_DIAGNOSE_ITERS
from opspilot.graph import _initial_state, build_graph
from opspilot.state import Intent
from opspilot.tools.service import ToolService

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE = REPO_ROOT / "eval" / "baselines" / "slice_baseline.json"


def _load_scenarios() -> list[dict[str, Any]]:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "build_goldens", REPO_ROOT / "data/answer_key/build_goldens.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.load_scenarios()


def _produced_refs(state: dict) -> set[str]:
    # evidence_by_id values are EvidenceItem; produced_refs is the accumulated tool trail across ALL
    # turns (diagnosis holds only the last turn, so a multi-turn LLM loop needs the trail here).
    refs = {ev.ref for ev in state.get("evidence_by_id", {}).values()}
    refs |= set(state.get("produced_refs") or [])
    diag = state.get("diagnosis")
    if diag is not None:
        for obs in diag.observations:
            refs |= set(obs.evidence_refs)
    return refs


def _implicated_entity(state: dict, root_by_incident: dict[str, str]) -> str | None:
    """The entity the hypothesis actually blames — read from the *structured* hypothesis, never
    parsed from prose. Prefer a deploy citation's service, then a log/metric service, then a
    dependency's from-side; for a known-issue fast path, reuse the matched incident's known root.
    """
    hyp = state.get("hypothesis")
    cites = list(hyp.citations) if hyp else []
    for wanted in (("deploys",), ("logs", "metrics")):
        for c in cites:
            if c.ref.split(":", 1)[0] in wanted:
                return c.ref.split(":")[1]
    for c in cites:
        if c.ref.startswith("deps:"):
            return c.ref.split(":", 1)[1].split("->")[0]
    matched = state.get("matched_incident", "")
    if matched.startswith("postmortem:"):
        return root_by_incident.get(matched.split(":", 1)[1])
    return None


def _score_one(scenario: dict, state: dict, root_by_incident: dict[str, str]) -> dict[str, float]:
    expected = set(scenario["expected_evidence"])
    produced = _produced_refs(state)
    report = state.get("report")
    citations = list(report.citations) if report else []
    diag = state.get("diagnosis")
    observations = diag.observations if diag is not None else []
    chain = scenario.get("impacted_chain") or []
    root = chain[0] if chain else None
    implicated = _implicated_entity(state, root_by_incident)

    # Agent-eval axes (Stage 4b): how *well* the loop behaves, not just what it concludes.
    # tool-selection precision — of the calls that executed, the fraction that produced evidence the
    # answer key expects (did the agent reach for the right tools rather than wander?).
    ok_obs = [o for o in observations if o.status == "ok"]
    selective = [o for o in ok_obs if expected & set(o.evidence_refs)]
    tool_selection = len(selective) / len(ok_obs) if ok_obs else 1.0
    # loop-termination — did the loop stop by its own stop rule, or exhaust the hard iteration cap
    # unresolved? A spinning agent that hits MAX_DIAGNOSE_ITERS without readiness scores 0.
    sufficiency = state.get("sufficiency")
    ready = bool(sufficiency.ready) if sufficiency is not None else False
    hit_cap = state.get("diagnose_iters", 0) >= MAX_DIAGNOSE_ITERS
    loop_termination = float((not hit_cap) or ready)

    # red-herring avoidance — reasoning quality that plain rca_correctness misses. Some incidents
    # carry a coincidental cause in the answer key (`red_herring`, e.g. inc-004's checkout deploy);
    # a good agent does NOT blame it. Scored 1 when the incident has no red herring OR the blamed
    # entity is not the red-herring's service. This is where the LLM beats the deterministic floor
    # even when the true (sometimes external) root is un-nameable, so rca_correctness only ties.
    red_herring = scenario.get("red_herring", "")
    rh_service = red_herring.split(":")[1] if ":" in red_herring else ""
    red_herring_avoided = float(not rh_service or implicated != rh_service)

    return {
        "routing_correct": float(state.get("intent") == scenario["expected_intent"]),
        "category_correct": float(state.get("category") == scenario["category"]),
        "evidence_recall": len(expected & produced) / len(expected) if expected else 1.0,
        "unsupported_rate": (
            len([c for c in citations if c not in produced]) / len(citations) if citations else 0.0
        ),
        "tool_calls_valid": (
            float(all(o.status == "ok" for o in observations)) if observations else 1.0
        ),
        "tool_selection": tool_selection,
        "loop_termination": loop_termination,
        "red_herring_avoided": red_herring_avoided,
        "iteration_ok": float(state.get("diagnose_iters", 0) <= MAX_DIAGNOSE_ITERS),
        # correctness is a SEPARATE axis from grounding: a report can cite real evidence and still
        # name the wrong root entity (inc-004's red herring). Root-entity match vs the answer key.
        "rca_correct": float(implicated is not None and root is not None and implicated == root),
    }


def _mcp_parity_ok() -> bool:
    from mcp.shared.memory import create_connected_server_and_client_session

    from opspilot.mcp.server import build_server

    svc = ToolService()
    server = build_server(svc)
    direct = json.loads(svc.call("get_incident", incident_id="inc-001").model_dump_json())

    async def _go() -> dict:
        async with create_connected_server_and_client_session(server) as client:
            result = await client.call_tool("get_incident", {"incident_id": "inc-001"})
            return json.loads(result.content[0].text)

    over_mcp = asyncio.run(_go())
    return over_mcp["status"] == direct["status"] and over_mcp["results"] == direct["results"]


def evaluate(implementation: str = "deterministic", *, model: Any = None) -> dict[str, Any]:
    from opspilot.diagnosis.planner import build_planner
    from opspilot.triage import build_triager

    app = build_graph()
    svc = ToolService()  # one shared service, injected into every run
    # `model` lets the caller inject a chat model for single_agent — a RecordingChatModel to capture
    # a cassette from the live model, or a ReplayChatModel to score deterministically in CI. Triage
    # and diagnosis share the model, so one cassette covers both LLM stages.
    planner = build_planner(implementation, model=model)  # unknown impl -> ValueError
    triager = build_triager(implementation, model=model)
    config = {"configurable": {"tool_service": svc, "planner": planner, "triager": triager}}
    scenarios = _load_scenarios()
    root_by_incident = {s["id"]: (s.get("impacted_chain") or [None])[0] for s in scenarios}
    per = [
        _score_one(s, app.invoke(_initial_state(
            {"incident_id": s["id"], "summary": s["alert"]["summary"]}), config=config),
            root_by_incident)
        for s in scenarios
    ]
    n = len(per)

    def mean(key: str) -> float:
        return round(sum(p[key] for p in per) / n, 4)

    # evidence_recall is measured only over scenarios that SHOULD be investigated (truth = novel).
    # A correctly fast-pathed known-issue recurrence gathers no diagnostic evidence by design, so
    # scoring its recall as 0 would reward the WRONG routing (investigating a known recurrence) —
    # see inc-007. Recall now measures investigation completeness where investigation is the job.
    def mean_over_novel(key: str) -> float:
        vals = [p[key] for p, s in zip(per, scenarios, strict=True)
                if s.get("expected_intent") == Intent.NOVEL_INVESTIGATION.value]
        return round(sum(vals) / len(vals), 4) if vals else 1.0

    return {
        "implementation": implementation,
        "n_scenarios": n,
        "routing_accuracy": mean("routing_correct"),
        "category_accuracy": mean("category_correct"),
        "evidence_recall": mean_over_novel("evidence_recall"),
        "rca_correctness": mean("rca_correct"),
        "red_herring_avoidance": mean("red_herring_avoided"),
        "unsupported_evidence_rate": mean("unsupported_rate"),
        "tool_call_validity": mean("tool_calls_valid"),
        "tool_selection_accuracy": mean("tool_selection"),
        "loop_termination_accuracy": mean("loop_termination"),
        "iteration_limit_compliance": mean("iteration_ok"),
        "mcp_parity": _mcp_parity_ok(),
    }


def main() -> None:
    scorecard = evaluate()
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(json.dumps(scorecard, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {BASELINE.relative_to(REPO_ROOT)}")
    print(json.dumps(scorecard, indent=2))


if __name__ == "__main__":
    main()
