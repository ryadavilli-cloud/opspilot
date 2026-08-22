"""What must be true before this process accepts a request, checked once at startup.

A deployed revision that starts with a setting missing does not fail where the setting is missing.
It fails later, inside an investigation, as an unavailable source or an unusable assessment, and
what an engineer then reads is a run that went wrong rather than a deployment that was never going
to work. Checking at startup moves the failure to the only place it can be read plainly.

Two kinds of problem are reported. A required setting that carries no value, and a setting whose
value names something that does not exist: a provider with no adapter, an exporter with no
implementation. The second matters because both of those resolve by falling back rather than by
raising, so a typo becomes a silently different runtime instead of a refusal.

No value is ever reported, only the name of the setting that holds it. A configuration error is
read by whoever can see the logs, which is not always whoever may see an endpoint or a key.
"""

from __future__ import annotations

from opspilot import config
from opspilot.llm.client import SELECTABLE_PROVIDERS

# Required only where the application talks to the deployed world. Locally the corpus fake, cassette
# replay, and the in-memory record stand in for each of these, and demanding them would refuse to
# start the very configuration the tests run.
_REQUIRED_WHEN_DEPLOYED = (
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_COSMOS_ENDPOINT",
)

_SETTING_VALUES = {
    "AZURE_OPENAI_ENDPOINT": lambda: config.AZURE_OPENAI_ENDPOINT,
    "AZURE_OPENAI_DEPLOYMENT": lambda: config.AZURE_OPENAI_DEPLOYMENT,
    "AZURE_COSMOS_ENDPOINT": lambda: config.COSMOS_ENDPOINT,
}

# What `OPSPILOT_LLM_PROVIDER` may select, imported from the factory that enforces it rather
# than restated here. The factory can also construct the offline judge's Claude adapter, but only
# for a caller that asks for it by name, so no configuration value can route the investigation
# onto the judge's model. Two tuples agreeing today is not the same as one answer: this check and
# the factory's refusal have to mean the same thing, and importing is what makes them.
_KNOWN_PROVIDERS = SELECTABLE_PROVIDERS
_KNOWN_EXPORTERS = ("none", "memory", "stdout")


def configuration_problems() -> list[str]:
    """Every configuration problem this process can see, each naming a setting and never a value.

    Returns rather than raises, so the caller decides what a problem means: a deployed revision
    refuses to start, and a local one is free to run against stand-ins.
    """
    problems = []

    if config.ENVIRONMENT != "local":
        for name in _REQUIRED_WHEN_DEPLOYED:
            if not _SETTING_VALUES[name]():
                problems.append(f"{name} is required when OPSPILOT_ENV is not local, and is unset")

    if config.LLM_PROVIDER.lower() not in _KNOWN_PROVIDERS:
        problems.append(
            "OPSPILOT_LLM_PROVIDER names nothing the runtime may select; it must be one of "
            f"{', '.join(_KNOWN_PROVIDERS)}"
        )

    if config.TRACE_EXPORTER not in _KNOWN_EXPORTERS:
        # This one resolves by falling back to the exporter that discards everything, so a typo
        # here is a revision that looks configured for telemetry and emits none.
        problems.append(
            f"OPSPILOT_TRACE_EXPORTER names no exporter; it must be one of "
            f"{', '.join(_KNOWN_EXPORTERS)}"
        )

    return problems


def startup_record() -> dict[str, str]:
    """What this revision is, for the first line it writes.

    The revision and the image are what identify a deployed process; the version alone does not,
    because two revisions can carry the same version and behave differently. Read from the platform
    where the platform supplies them, and left empty rather than guessed where it does not.
    """
    from opspilot import __version__

    return {
        "version": __version__,
        "environment": config.ENVIRONMENT,
        "revision": config.CONTAINER_APP_REVISION,
        "image": config.CONTAINER_IMAGE,
        "retrieval_backend": config.RETRIEVAL_BACKEND,
        "llm_provider": config.LLM_PROVIDER,
    }
