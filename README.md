# OpsPilot

Agentic incident-investigation assistant, built for Azure.

The accepted design — what the system is meant to become — lives in `docs/`.
`docs/status.md` records what is actually built against that design;
`docs/vertical-execution-plan.md` and `docs/horizontal-execution-plan.md` sequence the
remaining work.

The code in this repository runs one investigation as a single live request: a LangGraph
graph in which three model-directed roles propose and deterministic code authorizes, admits,
grounds, and persists. It is deployed on Azure. Parts of the accepted design are still to
come. See `docs/status.md` for what is built and what is not.

## Quickstart (local)

```bash
uv sync --group dev --group data                  # runtime + dev deps
uv run pytest -m "not llm" -q                      # CI-gated test lane
uv run uvicorn opspilot.api:app --reload           # serve the API (GET /health/live, /health/ready)
```

## Layout

```
src/opspilot/      # package: investigation graph, tools, retrieval, evidence, assessment, api
eval/              # the committed cassette and the recorder that produces it
data/              # RetailEase synthetic corpus: answer key, telemetry, alerts/incidents, KB
infra/             # Bicep IaC + GitHub Actions CD
tests/             # the deterministic suite
docs/              # the accepted design, decisions, and implementation status/plan
```
