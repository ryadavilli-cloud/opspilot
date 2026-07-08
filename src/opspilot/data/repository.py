"""Deterministic repository over the RetailEase corpus.

Tools query this layer instead of reading JSON files themselves. It loads the incident, alert,
and deployment records once and serves plain dicts; the typed contracts live in the tool layer.
This is the seam where the synthetic JSON source is later swapped for Azure Monitor / App Insights
/ Cosmos — the tools do not change, only the repository's backing store.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# src/opspilot/data/repository.py -> repo root is four parents up.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CORPUS = _REPO_ROOT / "data" / "synthetic"


def _load(path: Path, key: str) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"corpus file missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))[key]


class Repository:
    """In-memory view of the corpus. Construct once; query many times."""

    def __init__(self, corpus_dir: Path | None = None) -> None:
        corpus_dir = corpus_dir or Path(os.getenv("OPSPILOT_CORPUS_DIR", _DEFAULT_CORPUS))
        self._incidents = _load(corpus_dir / "incidents.json", "incidents")
        self._alerts = _load(corpus_dir / "alerts.json", "alerts")
        self._deployments = _load(corpus_dir / "deployments.json", "deployments")
        self._incident_by_id = {i["incident_id"]: i for i in self._incidents}

    # In tests we also build a Repository straight from records (e.g. to inject malformed rows).
    @classmethod
    def from_records(
        cls,
        incidents: list[dict] | None = None,
        alerts: list[dict] | None = None,
        deployments: list[dict] | None = None,
    ) -> Repository:
        obj = cls.__new__(cls)
        obj._incidents = incidents or []
        obj._alerts = alerts or []
        obj._deployments = deployments or []
        obj._incident_by_id = {i["incident_id"]: i for i in obj._incidents if "incident_id" in i}
        return obj

    def incident(self, incident_id: str) -> dict[str, Any] | None:
        return self._incident_by_id.get(incident_id)

    def alerts_for_incident(self, incident_id: str) -> list[dict[str, Any]]:
        return [a for a in self._alerts if a.get("incident_id") == incident_id]

    def deployments(self) -> list[dict[str, Any]]:
        return list(self._deployments)


_default: Repository | None = None


def default_repository() -> Repository:
    """Process-wide default repository (lazy, loaded once)."""
    global _default
    if _default is None:
        _default = Repository()
    return _default
