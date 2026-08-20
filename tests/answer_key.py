"""The authored answer key, loaded once for the tests that check the corpus against it.

Six test modules read these two files. They used to reach them through the golden builder, which
happened to expose loaders on its way to projecting the golden sets; when the projection went, the
loaders had no reason to live under `data/`. They are here instead, beside the other fixtures the
tests share, and the answer key is read directly rather than through a module that exists for
something else.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ANSWER_KEY_DIR = Path(__file__).resolve().parents[1] / "data" / "answer_key"


def _authored(name: str) -> Any:
    return yaml.safe_load((ANSWER_KEY_DIR / name).read_text(encoding="utf-8"))


def load_topology() -> dict[str, Any]:
    return dict(_authored("topology.yaml"))


def load_scenarios() -> list[dict[str, Any]]:
    return list(_authored("scenarios.yaml")["scenarios"])


def load_fixture() -> dict[str, Any]:
    """The benign fixture, which is evaluation corpus rather than an eighth scenario.

    Read by name and never through `load_scenarios()`, so it cannot drift into a scenario count.
    """
    return dict(_authored("benign_fixture.yaml")["fixture"])


TOPOLOGY = load_topology()
SCENARIOS = load_scenarios()
FIXTURE = load_fixture()
