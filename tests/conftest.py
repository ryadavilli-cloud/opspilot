"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from opspilot.obs import tracing


@pytest.fixture
def span_exporter() -> Iterator[tracing.InMemorySpanExporter]:
    """Capture emitted spans (Stage 5g / §23). Installs an in-memory exporter for the test and
    restores the previous one after, so 'a span was emitted under the parent trace_id with the
    required attributes' is asserted, not left to prose."""
    previous = tracing.get_exporter()
    exporter = tracing.InMemorySpanExporter()
    tracing.configure_exporter(exporter)
    try:
        yield exporter
    finally:
        tracing.configure_exporter(previous)
