"""Evaluation harness scaffold — plumbing before metrics (Phase 0).

Runs against an (initially empty) dataset and reports zero results. Real evaluators
(retrieval MRR, routing accuracy, groundedness, ...) are wired in from Phase 3 onward,
each introduced the moment its capability becomes real.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

# An evaluator takes an example and returns a {metric_name: score} mapping in [0, 1].
Evaluator = Callable[[dict[str, Any]], dict[str, float]]


def run_evals(
    dataset: Iterable[dict[str, Any]] | None = None,
    evaluators: list[Evaluator] | None = None,
) -> dict[str, Any]:
    """Run each evaluator over each example. Empty dataset -> n=0 (plumbing check)."""
    dataset = list(dataset or [])
    evaluators = evaluators or []

    results: list[dict[str, Any]] = []
    for example in dataset:
        scores: dict[str, float] = {}
        for evaluator in evaluators:
            scores.update(evaluator(example))
        results.append({"example": example, "scores": scores})

    return {"n": len(dataset), "evaluators": len(evaluators), "results": results}


if __name__ == "__main__":
    summary = run_evals()
    print(f"eval harness OK — ran {summary['evaluators']} evaluators over {summary['n']} examples")
