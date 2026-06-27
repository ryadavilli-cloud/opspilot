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
# Note: no BuildKit cache mount — az acr build uses the classic Docker builder.
COPY pyproject.toml uv.lock* README.md ./
RUN uv sync --no-install-project --no-dev

COPY src/ ./src/
RUN uv sync --no-dev

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "opspilot.api:app", "--host", "0.0.0.0", "--port", "8000"]
