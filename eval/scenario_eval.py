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
    # evidence_by_id values are EvidenceItem; diagnosis is a DiagnosisTrace (typed state).
    refs = {ev.ref for ev in state.get("evidence_by_id", {}).values()}
    diag = state.get("diagnosis")
    if diag is not None:
        for obs in diag.observations:
            refs |= set(obs.evidence_refs)
    return refs


def _score_one(scenario: dict, state: dict) -> dict[str, float]:
    expected = set(scenario["expected_evidence"])
    produced = _produced_refs(state)
    citations = (state.get("report") or {}).get("citations", [])
    diag = state.get("diagnosis")
    observations = diag.observations if diag is not None else []
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
        "iteration_ok": float(state.get("diagnose_iters", 0) <= MAX_DIAGNOSE_ITERS),
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


def evaluate(implementation: str = "deterministic") -> dict[str, Any]:
    app = build_graph()
    svc = ToolService()  # one shared service, injected into every run
    config = {"configurable": {"tool_service": svc}}
    scenarios = _load_scenarios()
    per = [
        _score_one(s, app.invoke(_initial_state(
            {"incident_id": s["id"], "summary": s["alert"]["summary"]}), config=config))
        for s in scenarios
    ]
    n = len(per)

    def mean(key: str) -> float:
        return round(sum(p[key] for p in per) / n, 4)

    return {
        "implementation": implementation,
        "n_scenarios": n,
        "routing_accuracy": mean("routing_correct"),
        "category_accuracy": mean("category_correct"),
        "evidence_recall": mean("evidence_recall"),
        "unsupported_evidence_rate": mean("unsupported_rate"),
        "tool_call_validity": mean("tool_calls_valid"),
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
