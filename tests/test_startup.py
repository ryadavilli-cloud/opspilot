"""What a process checks before it agrees to serve, and what it says about itself once it does.

The value of this check is entirely in when it happens. Every problem it reports would surface on
its own eventually, inside an investigation, as an unavailable source or a model that never
answers, which is the same failure wearing a costume that sends whoever is reading it somewhere
else. These assert that the check fires at startup and names the setting rather than the symptom.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from opspilot import config
from opspilot.api import app
from opspilot.obs import tracing
from opspilot.startup import configuration_problems, startup_record


def test_a_local_run_needs_none_of_the_deployed_settings(monkeypatch):
    """The stand-ins are the point of local. Demanding a deployed endpoint here would refuse to
    start the very configuration the deterministic lane runs on."""
    monkeypatch.setattr(config, "ENVIRONMENT", "local")
    monkeypatch.setattr(config, "AZURE_OPENAI_ENDPOINT", "")
    monkeypatch.setattr(config, "COSMOS_ENDPOINT", "")

    assert configuration_problems() == []


@pytest.mark.parametrize(
    "setting,attribute",
    [
        ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_ENDPOINT"),
        ("AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_DEPLOYMENT"),
        ("AZURE_COSMOS_ENDPOINT", "COSMOS_ENDPOINT"),
    ],
)
def test_a_deployed_run_refuses_a_required_setting_that_is_unset(monkeypatch, setting, attribute):
    monkeypatch.setattr(config, "ENVIRONMENT", "prod")
    monkeypatch.setattr(config, "AZURE_OPENAI_ENDPOINT", "https://example")
    monkeypatch.setattr(config, "AZURE_OPENAI_DEPLOYMENT", "chat")
    monkeypatch.setattr(config, "COSMOS_ENDPOINT", "https://example")
    monkeypatch.setattr(config, attribute, "")

    problems = configuration_problems()

    assert len(problems) == 1
    assert setting in problems[0]


def test_a_setting_naming_something_that_does_not_exist_is_refused_anywhere(monkeypatch):
    """Not gated on the environment, because a provider with no adapter is a mistake in any of
    them. This one resolves by raising later; the exporter below resolves by discarding silently,
    which is worse and the reason both are checked here rather than left to their call sites."""
    monkeypatch.setattr(config, "ENVIRONMENT", "local")
    monkeypatch.setattr(config, "LLM_PROVIDER", "ollama")

    problems = configuration_problems()

    assert len(problems) == 1
    assert "OPSPILOT_LLM_PROVIDER" in problems[0]


def test_a_constructible_but_unselectable_provider_is_refused(monkeypatch):
    """The model factory can build the judge's Claude adapter, but configuration may not route
    the runtime onto it: presence of an adapter is not permission to select it."""
    monkeypatch.setattr(config, "ENVIRONMENT", "local")
    monkeypatch.setattr(config, "LLM_PROVIDER", "claude")

    problems = configuration_problems()

    assert len(problems) == 1
    assert "OPSPILOT_LLM_PROVIDER" in problems[0]


def test_an_exporter_that_names_nothing_is_refused_rather_than_silently_discarding(monkeypatch):
    """The exporter falls back to the one that throws every span away. Without this a revision
    configured for telemetry emits none and looks configured."""
    monkeypatch.setattr(config, "ENVIRONMENT", "local")
    monkeypatch.setattr(config, "TRACE_EXPORTER", "applicationinsights")

    problems = configuration_problems()

    assert len(problems) == 1
    assert "OPSPILOT_TRACE_EXPORTER" in problems[0]


def test_no_problem_ever_reports_the_value_it_objected_to(monkeypatch):
    """A configuration error is read by whoever can see the logs, who is not always whoever may
    see an endpoint. The setting's name is what a reader needs; its value is what they do not."""
    monkeypatch.setattr(config, "ENVIRONMENT", "prod")
    monkeypatch.setattr(config, "AZURE_OPENAI_ENDPOINT", "")
    monkeypatch.setattr(config, "AZURE_OPENAI_DEPLOYMENT", "a-deployment-name")
    monkeypatch.setattr(config, "COSMOS_ENDPOINT", "https://secret-account.documents.azure.com")
    monkeypatch.setattr(config, "LLM_PROVIDER", "a-provider-that-is-not-real")

    report = " ".join(configuration_problems())

    assert "secret-account" not in report
    assert "a-deployment-name" not in report
    assert "a-provider-that-is-not-real" not in report


def test_the_application_refuses_to_start_on_a_configuration_problem(monkeypatch):
    """Asserted through the application rather than the function, because a check nothing runs is
    not a check. Starting the client is what runs the lifespan."""
    monkeypatch.setattr(config, "LLM_PROVIDER", "ollama")

    with pytest.raises(RuntimeError, match="refusing to start"), TestClient(app):
        pass  # pragma: no cover - the context manager raises on entry


def test_the_application_starts_when_the_configuration_holds():
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200


def test_the_startup_record_says_which_revision_and_image_this_is(monkeypatch):
    """Two revisions can carry the same version and behave differently, so the version alone does
    not identify a running process."""
    monkeypatch.setattr(config, "CONTAINER_APP_REVISION", "opspilot-api--0000042")
    monkeypatch.setattr(config, "CONTAINER_IMAGE", "registry.azurecr.io/opspilot:abc1234")

    record = startup_record()

    assert record["revision"] == "opspilot-api--0000042"
    assert record["image"] == "registry.azurecr.io/opspilot:abc1234"
    assert record["version"]


def test_the_startup_record_leaves_unknown_identity_empty_rather_than_guessing(monkeypatch):
    """Nothing supplies these outside a deployment. An invented value would be indistinguishable
    from a real one in the log that reads it."""
    monkeypatch.setattr(config, "CONTAINER_APP_REVISION", "")
    monkeypatch.setattr(config, "CONTAINER_IMAGE", "")

    record = startup_record()

    assert record["revision"] == ""
    assert record["image"] == ""


def test_the_configured_exporter_is_the_one_the_process_uses(monkeypatch):
    """A setting nothing applies is not configuration. The module is born with the exporter that
    discards every span, and nothing in the application had ever replaced it, so a revision set to
    emit telemetry emitted none and read as configured while doing so."""
    monkeypatch.setattr(config, "TRACE_EXPORTER", "memory")

    with TestClient(app):
        assert isinstance(tracing.get_exporter(), tracing.InMemorySpanExporter)


def test_a_run_reaches_the_configured_exporter(monkeypatch):
    """End to end through the seam rather than at it: something the application does has to arrive
    in the exporter the configuration chose."""
    monkeypatch.setattr(config, "TRACE_EXPORTER", "memory")

    with TestClient(app) as client:
        client.get("/health/live")
        exporter = tracing.get_exporter()
        assert isinstance(exporter, tracing.InMemorySpanExporter)
        with tracing.span("probe", trace_id="t-1"):
            pass
        assert [s.name for s in exporter.spans] == ["probe"]


def test_the_root_path_sends_a_local_visitor_to_the_screen(monkeypatch):
    """Nothing serves the platform's sign-in path locally, so sending a visitor there would send
    them nowhere."""
    monkeypatch.setattr(config, "ENVIRONMENT", "local")

    with TestClient(app, follow_redirects=False) as client:
        assert client.get("/").headers["location"] == "/investigation"


def test_the_root_path_sends_a_deployed_visitor_to_sign_in(monkeypatch):
    """Where the platform answers first, `/` is the one path left open, and the screen would
    answer a visitor holding no session with a bare 401. This hands them to the sign-in instead,
    which returns them to the screen, so the address worth sharing is still the bare one."""
    monkeypatch.setattr(config, "ENVIRONMENT", "prod")
    monkeypatch.setattr(config, "AZURE_OPENAI_ENDPOINT", "https://example")
    monkeypatch.setattr(config, "AZURE_OPENAI_DEPLOYMENT", "chat")
    monkeypatch.setattr(config, "COSMOS_ENDPOINT", "https://example")

    with TestClient(app, follow_redirects=False) as client:
        location = client.get("/").headers["location"]

    assert location.startswith("/.auth/login/aad")
    assert "investigation" in location
