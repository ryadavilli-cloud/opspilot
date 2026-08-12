"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fake_operational_records import FakeContainer, corpus_container

from opspilot.data.operational_records import OperationalRecords
from opspilot.obs import tracing
from opspilot.tools.service import ToolService


@pytest.fixture
def container() -> FakeContainer:
    """The whole authored corpus, container-shaped. Held as the container rather than the reader
    so a test can ask what it was given: which queries ran, and under what deadline."""
    return corpus_container()


@pytest.fixture
def records(container: FakeContainer) -> OperationalRecords:
    return OperationalRecords(container)


@pytest.fixture
def service(records: OperationalRecords) -> ToolService:
    """A tool service over the corpus container. Retrieval is left unbuilt; the modules that need
    it pass their own factory."""
    return ToolService(records)


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
