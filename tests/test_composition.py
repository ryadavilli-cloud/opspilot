"""Composition-root selection: OPSPILOT_IMPLEMENTATION picks the diagnosis pair the deployed app
injects, and single_agent falls back to the deterministic floor EXPLICITLY (recording why) when its
model cannot be built — never silently, so /version and the investigation runtime stay honest."""

from __future__ import annotations

from opspilot import composition, config
from opspilot.composition import build_diagnosis


def test_default_is_deterministic():
    d = build_diagnosis("deterministic")
    assert d.implementation == "deterministic" and d.requested == "deterministic"
    assert d.planner.name == "deterministic" and d.triager.name == "deterministic"
    assert d.provider is None and d.model_id is None and d.fallback_reason is None


def test_single_agent_missing_azure_endpoint_falls_back_explicitly(monkeypatch):
    # Pretend the optional `llm` deps are present so the blocker reaches the Azure-endpoint check —
    # otherwise, in a lane without the llm group, it stops at "openai SDK missing" first and this
    # test would assert on the wrong reason.
    monkeypatch.setattr(composition.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(config, "LLM_PROVIDER", "azure")
    monkeypatch.setattr(config, "AZURE_OPENAI_ENDPOINT", "")
    d = build_diagnosis("single_agent")
    assert d.implementation == "deterministic"        # fell back to the floor
    assert d.requested == "single_agent"              # but records what was asked for
    assert d.fallback_reason and "AZURE_OPENAI_ENDPOINT" in d.fallback_reason
    assert d.planner.name == "deterministic" and d.triager.name == "deterministic"


def test_single_agent_missing_llm_dependency_falls_back_explicitly(monkeypatch):
    monkeypatch.setattr(
        composition,
        "_single_agent_blocker",
        lambda: "optional 'llm' dependency group is not installed (openai SDK missing)",
    )
    d = build_diagnosis("single_agent")
    assert d.implementation == "deterministic"
    assert d.requested == "single_agent"
    assert d.fallback_reason and "llm" in d.fallback_reason.lower()


def test_single_agent_builds_the_llm_pair_when_configured(monkeypatch):
    # A fake ChatModel keeps this ML-free: no live provider, no openai SDK import.
    class _FakeModel:
        model_id = "gpt-4o-mini"

    import opspilot.llm.client as client

    monkeypatch.setattr(config, "LLM_PROVIDER", "azure")
    monkeypatch.setattr(composition, "_single_agent_blocker", lambda: None)
    monkeypatch.setattr(client, "build_chat_model", lambda *a, **k: _FakeModel())

    d = build_diagnosis("single_agent")
    assert d.implementation == "single_agent" and d.requested == "single_agent"
    assert d.provider == "azure" and d.model_id == "gpt-4o-mini"
    assert d.planner.name == "single_agent" and d.triager.name == "single_agent"
    assert d.fallback_reason is None


def test_single_agent_build_error_falls_back_explicitly(monkeypatch):
    import opspilot.llm.client as client

    def _boom(*_a, **_k):
        raise RuntimeError("model construction blew up")

    monkeypatch.setattr(composition, "_single_agent_blocker", lambda: None)
    monkeypatch.setattr(client, "build_chat_model", _boom)

    d = build_diagnosis("single_agent")
    assert d.implementation == "deterministic"
    assert d.fallback_reason and "model construction blew up" in d.fallback_reason
