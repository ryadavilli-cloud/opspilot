# OpsPilot

**Production-ready agentic AI incident-investigation assistant, on Azure.**

OpsPilot ingests a cloud incident alert, investigates it like an on-call engineer, and
produces an evidence-backed root-cause report — grounded in runbooks, past incidents, and
live telemetry, with a human approval gate before anything consequential, and full
observability, evaluation, guardrails, and cost controls around it.

> 🚧 **Status: scaffolding (Phase 0).** This README is a skeleton — it is finalized later,
> derived from the architecture and actual progress. See `docs/architecture.md` and
> `docs/execution-plan.md` for the canonical design and build plan.

## Quickstart (local)

```bash
uv sync                 # create the venv and install deps
uv run pytest -q        # run the scaffold tests
uv run uvicorn opspilot.api:app --reload   # serve the API (GET /health)
```

## Layout

```
src/opspilot/      # package: graph, nodes, tools, guardrails, ops, api, config
eval/              # evaluation harness (runnable; evaluators added per phase)
data/              # corpora (runbooks, past incidents, telemetry) — populated Phase 2
infra/             # Bicep IaC — populated Phase 1.5 onward
tests/             # deterministic safety-net tests
docs/              # architecture + execution plan
```

## Documentation

- **Architecture:** `docs/architecture.md`
- **Execution plan:** `docs/execution-plan.md`
