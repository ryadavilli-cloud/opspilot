"""Project the RetailEase answer key into the eval golden sets.

The answer key (topology.yaml + scenarios.yaml) is the single source of truth. This script
is a *deterministic projection* of it into the two files the eval harness scores against:

  eval/golden_incidents.json   — labeled incidents for routing / correctness / groundedness evals
  eval/golden_retrieval.json   — labeled queries -> relevant KB doc ids for retrieval (MRR/P@K)

The JSON is generated, never hand-edited. tests/test_answer_key.py regenerates in-memory and
asserts the committed files are in sync, so drift between the answer key and the goldens fails CI.

Run:  python data/answer_key/build_goldens.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

ANSWER_KEY_DIR = Path(__file__).resolve().parent
REPO_ROOT = ANSWER_KEY_DIR.parents[1]
EVAL_DIR = REPO_ROOT / "eval"

TOPOLOGY_PATH = ANSWER_KEY_DIR / "topology.yaml"
SCENARIOS_PATH = ANSWER_KEY_DIR / "scenarios.yaml"
GOLDEN_INCIDENTS_PATH = EVAL_DIR / "golden_incidents.json"
GOLDEN_RETRIEVAL_PATH = EVAL_DIR / "golden_retrieval.json"


def load_topology() -> dict[str, Any]:
    return yaml.safe_load(TOPOLOGY_PATH.read_text(encoding="utf-8"))


def load_scenarios() -> list[dict[str, Any]]:
    return yaml.safe_load(SCENARIOS_PATH.read_text(encoding="utf-8"))["scenarios"]


def build_incident_goldens(scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One labeled incident per scenario — the answer key for end-to-end evals."""
    out: list[dict[str, Any]] = []
    for s in scenarios:
        out.append(
            {
                "incident_id": s["id"],
                "title": s["title"],
                "type": s["type"],
                "alert": s["alert"],
                "expected_severity": s["severity"],
                "expected_category": s["category"],
                "expected_intent": s["expected_intent"],
                "expected_match": s["expected_match"],
                "expected_root_cause": " ".join(s["root_cause"].split()),
                "expected_impacted_chain": s["impacted_chain"],
                "expected_evidence_refs": s["expected_evidence"],
                "expected_retrieval_ids": s["expected_retrieval"],
                "red_herring": s.get("red_herring"),
            }
        )
    return out


def build_retrieval_goldens(scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One labeled query per scenario — relevant KB doc ids for retrieval metrics."""
    out: list[dict[str, Any]] = []
    for s in scenarios:
        out.append(
            {
                "query_id": s["id"],
                "query": " ".join(s["alert"]["summary"].split()),
                "relevant_doc_ids": s["expected_retrieval"],
            }
        )
    return out


def _dump(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    scenarios = load_scenarios()
    _dump(GOLDEN_INCIDENTS_PATH, build_incident_goldens(scenarios))
    _dump(GOLDEN_RETRIEVAL_PATH, build_retrieval_goldens(scenarios))
    print(
        f"wrote {GOLDEN_INCIDENTS_PATH.relative_to(REPO_ROOT)} and "
        f"{GOLDEN_RETRIEVAL_PATH.relative_to(REPO_ROOT)} from {len(scenarios)} scenarios"
    )


if __name__ == "__main__":
    main()
