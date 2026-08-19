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
# `--group llm` adds the OpenAI SDK and azure-identity so the runtime reaches Azure OpenAI
# keyless, as the Container App's managed identity. Cosmos access is a base dependency rather
# than a group, because every read the runtime makes goes through it. Nothing else is
# installed, so the image is lean and downloads no models. Note: no BuildKit cache mount,
# since az acr build uses the classic Docker builder.
COPY pyproject.toml uv.lock* README.md ./
RUN uv sync --no-install-project --no-dev --group llm

COPY src/ ./src/
RUN uv sync --no-dev --group llm

# No corpus data ships in the image. The KB and the operational corpus are both read from Cosmos
# (the `knowledge` and `operational-records` containers) rather than from files, so an image that
# shipped either could not fall back to it. Not the answer key, distractors, calibration datasets,
# eval baselines, generators, or docs either (see .dockerignore).

EXPOSE 8000
# --frozen --no-dev --group llm: run against the locked runtime environment exactly as built.
# Without --frozen, `uv run` re-syncs at startup (network); without the group it would prune
# those packages to match the default set, leaving the runtime unable to reach the deployment.
CMD ["uv", "run", "--frozen", "--no-dev", "--group", "llm", "uvicorn", "opspilot.api:app", "--host", "0.0.0.0", "--port", "8000"]
