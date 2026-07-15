"""Deterministic repository over the RetailEase corpus.

Tools query this layer instead of reading files themselves. It loads incidents, alerts,
deployments, logs, metric series, and dependency edges once and serves plain dicts; the typed
contracts live in the tool layer. This is the seam where the synthetic corpus is later swapped for
Azure Monitor / App Insights / Cosmos — the tools do not change, only the repository's backing.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opspilot.config import CORPUS_DIR

# The operational corpus files a runtime image must ship. Validated up front so a missing
# deployment surfaces one complete diagnostic, not a FileNotFoundError on first tool call.
CORPUS_FILES = (
    "incidents.json",
    "alerts.json",
    "deployments.json",
    "logs.jsonl",
    "metrics.json",
    "dependencies.json",
)


@dataclass(frozen=True)
class RuntimeAssetStatus:
    """Which required corpus files are present under a directory, and which are missing."""

    root: Path
    present: tuple[str, ...]
    missing: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.missing


def validate_corpus(corpus_dir: Path) -> RuntimeAssetStatus:
    """Check every required corpus file once, reporting all that are missing together."""
    present: list[str] = []
    missing: list[str] = []
    for name in CORPUS_FILES:
        (present if (corpus_dir / name).exists() else missing).append(name)
    return RuntimeAssetStatus(Path(corpus_dir), tuple(present), tuple(missing))


def _resolve_corpus_dir(corpus_dir: Path | str | None) -> Path:
    if corpus_dir is not None:
        return Path(corpus_dir)
    env = os.getenv("OPSPILOT_CORPUS_DIR")
    return Path(env) if env else CORPUS_DIR


def _load(path: Path, key: str) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))[key]


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class Repository:
    """In-memory view of the corpus. Construct once; query many times."""

    def __init__(self, corpus_dir: Path | str | None = None) -> None:
        corpus_dir = _resolve_corpus_dir(corpus_dir)
        status = validate_corpus(corpus_dir)
        if not status.ok:
            raise FileNotFoundError(
                f"corpus incomplete at {corpus_dir}: missing {', '.join(status.missing)}")
        self._incidents = _load(corpus_dir / "incidents.json", "incidents")
        self._alerts = _load(corpus_dir / "alerts.json", "alerts")
        self._deployments = _load(corpus_dir / "deployments.json", "deployments")
        self._logs = _load_jsonl(corpus_dir / "logs.jsonl")
        self._metrics = _load(corpus_dir / "metrics.json", "series")
        self._edges = _load(corpus_dir / "dependencies.json", "edges")
        self._incident_by_id = {i["incident_id"]: i for i in self._incidents}

    @classmethod
    def from_records(
        cls,
        incidents: list[dict] | None = None,
        alerts: list[dict] | None = None,
        deployments: list[dict] | None = None,
        logs: list[dict] | None = None,
        metrics: list[dict] | None = None,
        edges: list[dict] | None = None,
    ) -> Repository:
        """Build a repository straight from records — used in tests to inject edge cases."""
        obj = cls.__new__(cls)
        obj._incidents = incidents or []
        obj._alerts = alerts or []
        obj._deployments = deployments or []
        obj._logs = logs or []
        obj._metrics = metrics or []
        obj._edges = edges or []
        obj._incident_by_id = {i["incident_id"]: i for i in obj._incidents if "incident_id" in i}
        return obj

    def incident(self, incident_id: str) -> dict[str, Any] | None:
        return self._incident_by_id.get(incident_id)

    def alerts_for_incident(self, incident_id: str) -> list[dict[str, Any]]:
        return [a for a in self._alerts if a.get("incident_id") == incident_id]

    def deployments(self) -> list[dict[str, Any]]:
        return list(self._deployments)

    def logs(self) -> list[dict[str, Any]]:
        return list(self._logs)

    def metric_series(self) -> list[dict[str, Any]]:
        return list(self._metrics)

    def edges(self) -> list[dict[str, Any]]:
        return list(self._edges)


_default: Repository | None = None


def default_repository() -> Repository:
    """Process-wide default repository (lazy, loaded once)."""
    global _default
    if _default is None:
        _default = Repository()
    return _default
