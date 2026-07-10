"""Retrieval evaluation — MRR, Precision@k, Recall@k over eval/golden_retrieval.json.

Scores a retriever in a given mode against the labeled queries. `main` runs both modes so the
"hybrid beats vector-only" proof is a single reproducible table.
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN = REPO_ROOT / "eval" / "golden_retrieval.json"


def load_golden() -> list[dict[str, Any]]:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def evaluate(retriever, golden: list[dict], mode: str = "dense", k: int = 5) -> dict[str, Any]:
    ranks, precisions, recalls = [], [], []
    for ex in golden:
        relevant = set(ex["relevant_doc_ids"])
        ranked = [h.doc_id for h in getattr(retriever, mode)(ex["query"], k=k)]
        first = next((i + 1 for i, d in enumerate(ranked) if d in relevant), None)
        ranks.append(1.0 / first if first else 0.0)
        found = set(ranked) & relevant
        precisions.append(len(found) / k)
        recalls.append(len(found) / len(relevant) if relevant else 0.0)
    return {
        "mode": mode, "k": k, "n": len(golden),
        "MRR": round(mean(ranks), 4),
        f"P@{k}": round(mean(precisions), 4),
        f"Recall@{k}": round(mean(recalls), 4),
    }


def main() -> None:
    from opspilot.retrieval.retriever import Retriever

    golden = load_golden()
    print(f"indexing corpus + distractors, scoring {len(golden)} queries…")
    retriever = Retriever(include_distractors=True)
    for mode in ("dense", "hybrid"):
        r = evaluate(retriever, golden, mode=mode, k=5)
        print(f"  {r['mode']:7s}  MRR={r['MRR']:.4f}  "
              f"P@5={r['P@5']:.4f}  Recall@5={r['Recall@5']:.4f}")


if __name__ == "__main__":
    main()
