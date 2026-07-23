# syntax=docker/dockerfile:1
# Multi-stage build using uv for fast, reproducible installs.
FROM python:3.12-slim AS base

# uv from the official distroless image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Install dependencies first (cached layer), then the project.
# `--group llm` adds the OpenAI SDK + azure-identity so the runtime can drive the single_agent path
# against Azure OpenAI (keyless, via the Container App's managed identity). `--group checkpoint`
# adds the Cosmos DB backends (LangGraph checkpointer + InvestigationRepository, Stage 5b/5c); both
# are live in prod (OPSPILOT_CHECKPOINTER=cosmos, OPSPILOT_INVESTIGATION_REPOSITORY=cosmos), and
# without this group their lazy imports would ImportError on the first /investigations request. The
# heavy dense/rerank ML stack (eval group) is still excluded, so the image stays lean and downloads
# no models. Note: no BuildKit cache mount — az acr build uses the classic Docker builder.
COPY pyproject.toml uv.lock* README.md ./
RUN uv sync --no-install-project --no-dev --group llm --group checkpoint

COPY src/ ./src/
RUN uv sync --no-dev --group llm --group checkpoint

# Package only the operational runtime data: the synthetic corpus and the KB. Not the answer key,
# distractors, calibration datasets, eval baselines, generators, or docs (see .dockerignore).
COPY data/synthetic/ ./data/synthetic/
COPY data/kb/ ./data/kb/

# Point the runtime at the packaged data explicitly (never inferred from the source-tree layout),
# and select the lexical BM25 backend so the image needs no embedding model.
ENV OPSPILOT_CORPUS_DIR=/app/data/synthetic \
    OPSPILOT_KB_DIR=/app/data/kb \
    OPSPILOT_RETRIEVAL_BACKEND=bm25

EXPOSE 8000
# --frozen --no-dev --group llm --group checkpoint: run against the locked runtime environment
# exactly as built. Without --frozen, `uv run` re-syncs at startup (network); without both groups
# it would prune their packages to match the default group set, breaking the single_agent path and
# the Cosmos-backed investigation repository respectively.
CMD ["uv", "run", "--frozen", "--no-dev", "--group", "llm", "--group", "checkpoint", "uvicorn", "opspilot.api:app", "--host", "0.0.0.0", "--port", "8000"]
