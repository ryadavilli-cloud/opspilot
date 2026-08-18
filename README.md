# OpsPilot

Agentic incident-investigation assistant, built for Azure.

The accepted design — what the system is meant to become — lives in `docs/`.
`docs/status.md` records what is actually built against that design;
`docs/vertical-execution-plan.md` and `docs/horizontal-execution-plan.md` sequence the
remaining work.

The code in this repository currently implements an earlier architecture: a LangGraph
pipeline with a human-in-the-loop approval gate, per-step durable checkpointing, and an
asynchronous submit/poll job API. It runs end to end (deterministic and LLM-driven
diagnosis paths, an operator console) and is deployed on Azure, but does
not yet match the accepted design. See `docs/status.md` for the full reconciliation.

## Quickstart (local)

```bash
uv sync --group dev --group data                  # runtime + dev deps
uv run pytest -m "not llm" -q                      # CI-gated test lane
uv run uvicorn opspilot.api:app --reload           # serve the API (GET /health/live, /health/ready)
```

## Layout

```
src/opspilot/      # package: graph, nodes, tools, retrieval, diagnosis, guardrails, mcp, api, config
eval/              # evaluation harness + committed baselines (retrieval + scenario scorecards)
data/              # RetailEase synthetic corpus: answer key, telemetry, alerts/incidents, KB
infra/             # Bicep IaC + GitHub Actions CD
tests/             # deterministic safety-net + scenario regression gate
docs/              # the accepted design, decisions, and implementation status/plan
```
