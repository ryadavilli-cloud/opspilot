"""Retrieval evaluation — MRR, Precision@k, Recall@k over eval/golden_retrieval.json.

Scores a retriever in a given mode against the labeled queries. `main` runs every mode
(dense → hybrid → rerank) so the "hybrid beats vector-only" and "rerank lifts precision"
proofs are a single reproducible table, and writes the measured scorecard to
eval/baselines/retrieval_scorecard.json (the committed, deliberately-ratcheted baseline).
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN = REPO_ROOT / "eval" / "golden_retrieval.json"
SCORECARD = REPO_ROOT / "eval" / "baselines" / "retrieval_scorecard.json"
MODES = ("dense", "hybrid", "rerank")


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


def score_all(retriever, golden: list[dict], k: int = 5) -> dict[str, dict[str, Any]]:
    """Score every mode; the shared retriever indexes the corpus once."""
    return {mode: evaluate(retriever, golden, mode=mode, k=k) for mode in MODES}


def main(write: bool = True) -> None:
    from opspilot.config import EMBEDDING_MODEL, RERANKER_MODEL, TARGETS
    from opspilot.retrieval.embeddings import DEFAULT_MODEL
    from opspilot.retrieval.reranker import DEFAULT_RERANKER
    from opspilot.retrieval.retriever import Retriever

    golden = load_golden()
    print(f"indexing corpus + distractors, scoring {len(golden)} queries...")
    retriever = Retriever(include_distractors=True)
    results = score_all(retriever, golden, k=5)
    for mode in MODES:
        r = results[mode]
        print(f"  {r['mode']:7s}  MRR={r['MRR']:.4f}  "
              f"P@5={r['P@5']:.4f}  Recall@5={r['Recall@5']:.4f}")

    best = max(results.values(), key=lambda r: r["MRR"])

    if write:
        scorecard = {
            "embed_model": DEFAULT_MODEL,
            "reranker_model": DEFAULT_RERANKER,
            # config's declared prod defaults, recorded for the local<->prod parity note
            "prod_embed_model": EMBEDDING_MODEL,
            "prod_reranker_model": RERANKER_MODEL,
            "mrr_target": TARGETS.mrr_min,
            "best_mode": best["mode"],
            "best_mrr": best["MRR"],
            "target_met": best["MRR"] >= TARGETS.mrr_min,
            "modes": results,
        }
        SCORECARD.parent.mkdir(parents=True, exist_ok=True)
        SCORECARD.write_text(json.dumps(scorecard, indent=2) + "\n", encoding="utf-8")
        print(f"  wrote {SCORECARD.relative_to(REPO_ROOT)}")

    met = "MET" if best["MRR"] >= TARGETS.mrr_min else "not met"
    print(f"  target MRR>={TARGETS.mrr_min}: best={best['mode']} MRR={best['MRR']:.4f} -> {met}")


if __name__ == "__main__":
    main()
