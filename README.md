# OpsPilot

**Production-ready agentic AI incident-investigation assistant, on Azure.**

OpsPilot ingests a cloud incident alert, investigates it like an on-call engineer, and
produces an evidence-backed root-cause report — grounded in runbooks, past incidents, and
live telemetry, with a human approval gate before anything consequential, and full
observability, evaluation, guardrails, and cost controls around it.

> **Status: deterministic connected slice.** A synthetic incident flows ingest → triage →
> hybrid retrieval → one diagnostic cycle → grounded report → citation guardrail, end to end,
> with no LLM in the loop yet — the deterministic baseline the model must beat. Hybrid + reranked
> retrieval is measured against a committed scorecard (`eval/baselines/`).

## Quickstart (local)

```bash
uv sync                       # runtime + dev deps
uv run pytest -q              # full test suite (retrieval/eval tests skip without the extras)
uv run uvicorn opspilot.api:app --reload   # serve the API (GET /health)

uv sync --group eval          # add the retrieval/eval ML stack (sentence-transformers, BM25)
uv run python eval/retrieval_eval.py       # score dense / hybrid / rerank + write the scorecard
```

## Layout

```
src/opspilot/      # package: graph, nodes, tools, retrieval, diagnosis, guardrails, mcp, api, config
eval/              # evaluation harness + committed baselines (retrieval + scenario scorecards)
data/              # RetailEase synthetic corpus: answer key, telemetry, alerts/incidents, KB
infra/             # Bicep IaC + GitHub Actions CD
tests/             # deterministic safety-net + scenario regression gate
```
