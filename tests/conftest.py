"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fake_operational_records import FakeContainer, corpus_container

from opspilot import api
from opspilot.data import knowledge_records, operational_records
from opspilot.data.operational_records import OperationalRecords
from opspilot.llm import client as llm_client
from opspilot.obs import tracing
from opspilot.retrieval import embeddings as query_embeddings
from opspilot.retrieval import retriever as retriever_module
from opspilot.tools import service as tool_service_module
from opspilot.tools.service import ToolService


@pytest.fixture(autouse=True)
def _no_deployed_container(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test may fall through to the deployed container.

    `ToolService()` and the nodes' `_svc(None)` both default to `default_operational_records()`,
    which builds a Cosmos client from the optional Azure packages. A test that reaches it is not
    deterministic, and the way that surfaces depends on which dependency groups happen to be
    installed: an ImportError where they are absent, a live credential lookup where they are not.
    Neither says what actually went wrong, and the lane that installs the most groups is the one
    that fails.

    Failing here names the defect instead: the test did not inject a source.

    Patched at every module that imported the name, not only where it is defined, because
    `from ... import default_operational_records` binds it into the importing module at import
    time and a patch on the source module would never be consulted.
    """

    def _refuse() -> OperationalRecords:
        raise AssertionError(
            "a test reached the deployed operational-records container. Inject a source: "
            "ToolService(corpus_records()), or pass one through the node config as "
            "{'configurable': {'tool_service': ...}}"
        )

    for module in (operational_records, tool_service_module, api):
        monkeypatch.setattr(module, "default_operational_records", _refuse)

    def _refuse_retriever() -> Any:
        raise AssertionError(
            "a test reached the deployed knowledge retriever. Inject one: "
            "ToolService(records, retriever_factory=knowledge_retriever) from fake_knowledge."
        )

    # `ToolService._get_retriever()` imports `default_retriever` locally (inside the function, not
    # at module load), so only the defining module needs patching: the local import re-resolves the
    # attribute from `retriever_module` on every call, unlike a module-level `from x import y`.
    monkeypatch.setattr(retriever_module, "default_retriever", _refuse_retriever)
    monkeypatch.setattr(retriever_module, "default_knowledge_records", _refuse_retriever)
    monkeypatch.setattr(knowledge_records, "default_knowledge_records", _refuse_retriever)
    monkeypatch.setattr(retriever_module, "default_query_embedder", _refuse_retriever)
    monkeypatch.setattr(query_embeddings, "default_query_embedder", _refuse_retriever)


@pytest.fixture(autouse=True)
def _no_live_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test may fall through to a live model provider.

    The synthesis dependency, the planner, the triager, and the composition root all reach
    `build_chat_model()` with no provider, which resolves whatever `OPSPILOT_LLM_PROVIDER` names
    and defaults to Ollama. Construction takes no network, so a missing injection does not surface
    until `.complete()` blocks on a connection that never resolves. That reads as a slow suite
    rather than as a missing seam, and sends the next hour into the wrong investigation.

    Refusing the config-resolved call names the defect instead: the test did not inject a model.
    A call naming its provider is left alone, because it is constructing a known type deliberately
    rather than reaching for whatever the environment happens to hold.

    The resolved synthesis model is a process-wide singleton, so it is reset per test as well: one
    test that obtained a model must not leave it installed for every test collected after it.
    """
    live = llm_client.build_chat_model

    def _refuse(provider: str | None = None, **kwargs: Any) -> Any:
        if provider is None:
            raise AssertionError(
                "a test reached the config-resolved live model. Inject one: override "
                "get_synthesis_model, pass model= to the planner or triager, or name a provider."
            )
        return live(provider, **kwargs)

    monkeypatch.setattr(llm_client, "build_chat_model", _refuse)
    monkeypatch.setattr(api, "_synthesis_model", None)


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
    """Capture emitted spans. Installs an in-memory exporter for the test and
    restores the previous one after, so 'a span was emitted under the parent trace_id with the
    required attributes' is asserted, not left to prose."""
    previous = tracing.get_exporter()
    exporter = tracing.InMemorySpanExporter()
    tracing.configure_exporter(exporter)
    try:
        yield exporter
    finally:
        tracing.configure_exporter(previous)
