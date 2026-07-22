"""InvestigationRepository factory — proves the factory routes backends (unknown fails loud), and
that the `cosmos` backend's config guard fires before the optional Cosmos SDK import, mirroring
`test_checkpointer.py`'s treatment of the checkpointer's own `cosmos` backend.

ML-free / Azure-free: `memory` needs nothing; `cosmos` is validated only for its config guard (a
live Cosmos test would need Azure + the optional `checkpoint` group)."""

from __future__ import annotations

import pytest

from opspilot import config
from opspilot.investigations import InMemoryInvestigationRepository
from opspilot.repository import build_investigation_repository


def test_memory_backend_builds_an_in_memory_repository():
    assert isinstance(build_investigation_repository("memory"), InMemoryInvestigationRepository)


def test_unknown_backend_fails_loud():
    with pytest.raises(ValueError, match="unknown investigation repository backend"):
        build_investigation_repository("redis")


def test_cosmos_requires_an_endpoint(monkeypatch):
    # The config guard must fire before the optional import, so this holds even without the
    # `checkpoint` group installed (as in CI).
    monkeypatch.setattr(config, "COSMOS_ENDPOINT", "")
    with pytest.raises(ValueError, match="AZURE_COSMOS_ENDPOINT"):
        build_investigation_repository("cosmos")
