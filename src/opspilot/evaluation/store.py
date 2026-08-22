"""The Evaluation Record seam: save one kept run, read it back, and list what is kept.

Passive, like the investigation record it mirrors: it stores what it is given and answers reads.
It decides nothing about a run and nothing about an investigation.

A second save of the same `run_id` is refused. A kept run is a point-in-time reading and is never
edited, so overwriting one would replace a result someone may already have read with a different
one under the same name. The refusal raises, for the same reason the record's does: a caller that
ignores a returned status would carry on believing it had kept something.

Two backends. The in-memory one serves tests and holds each run as the document it would be
written as, revalidated on read, so a field that cannot survive storage fails here rather than only
against Cosmos. The Cosmos one is the durable store: one container, one document per run,
partitioned by `run_id`. The evaluation runner writes to it under its own principal; the
application holds read on that container and nothing more, which is what keeps a request from
ever writing a run.
"""

from __future__ import annotations

from typing import Any, Protocol

from opspilot import config
from opspilot.evaluation.record import EvaluationRun, EvaluationRunSummary


class RunAlreadySaved(Exception):
    """An evaluation run was saved twice under one identifier."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"evaluation run {run_id!r} is already saved")
        self.run_id = run_id


class EvaluationRunRepository(Protocol):
    """Passive persistence of kept runs. Every backend satisfies exactly this."""

    def save(self, run: EvaluationRun) -> None:
        """Persist one kept run. Raises `RunAlreadySaved` if the identifier is taken."""
        ...

    def get(self, run_id: str) -> EvaluationRun | None:
        """The kept run, or None where nothing was ever kept under that identifier."""
        ...

    def list_runs(self) -> list[EvaluationRunSummary]:
        """Every kept run as a summary, newest first."""
        ...


def _summary(document: dict[str, Any]) -> EvaluationRunSummary:
    # Unknown keys are ignored, so a whole document and a projected row both validate.
    return EvaluationRunSummary.model_validate(document)


class InMemoryEvaluationRuns:
    """Kept runs held in process, keyed by run identity."""

    def __init__(self) -> None:
        self._runs: dict[str, dict[str, Any]] = {}

    def save(self, run: EvaluationRun) -> None:
        if run.run_id in self._runs:
            raise RunAlreadySaved(run.run_id)
        self._runs[run.run_id] = run.model_dump(mode="json")

    def get(self, run_id: str) -> EvaluationRun | None:
        document = self._runs.get(run_id)
        if document is None:
            return None
        return EvaluationRun.model_validate(document)

    def list_runs(self) -> list[EvaluationRunSummary]:
        summaries = [_summary(document) for document in reversed(self._runs.values())]
        return sorted(summaries, key=lambda summary: summary.taken_at, reverse=True)


# The listing reads the summary fields and nothing else, across every partition, newest first.
_SUMMARY_QUERY = (
    "SELECT c.run_id, c.taken_at, c.label, c.configuration FROM c ORDER BY c.taken_at DESC"
)


class CosmosEvaluationRuns:
    """Kept runs in the evaluation container.

    The container object is injected, as it is for the investigation record, so a test holds a
    stand-in with the same surface and the deployed path holds a real container. Cosmos needs an
    `id` on every document; the run's own identity is attached on the way out rather than a second
    key invented, and the container's bookkeeping properties are ignored on the way back.
    """

    def __init__(self, container: Any) -> None:
        self._container = container

    def save(self, run: EvaluationRun) -> None:
        document = run.model_dump(mode="json")
        document["id"] = run.run_id
        try:
            self._container.create_item(body=document)
        except Exception as exc:  # noqa: BLE001 - one write per run; a conflict is the refusal
            if _status(exc) == 409:
                raise RunAlreadySaved(run.run_id) from exc
            raise

    def get(self, run_id: str) -> EvaluationRun | None:
        try:
            document = self._container.read_item(item=run_id, partition_key=run_id)
        except Exception as exc:  # noqa: BLE001 - absent is an answer, not a failure
            if _status(exc) == 404:
                return None
            raise
        return EvaluationRun.model_validate(document)

    def list_runs(self) -> list[EvaluationRunSummary]:
        rows = self._container.query_items(query=_SUMMARY_QUERY, enable_cross_partition_query=True)
        return [_summary(row) for row in rows]


def _status(exc: Exception) -> int | None:
    code = getattr(exc, "status_code", None)
    return code if isinstance(code, int) else None


def default_evaluation_runs() -> CosmosEvaluationRuns:
    """The store over the deployed container, built by whoever needs it: the application to read,
    the evaluation runner to write. Which of the two a caller may do is decided by the role the
    caller's identity holds on the container, not by anything here.

    The Cosmos imports are local so that importing this module needs no credential.
    """
    from azure.cosmos import CosmosClient
    from azure.identity import DefaultAzureCredential

    client = CosmosClient(config.COSMOS_ENDPOINT, credential=DefaultAzureCredential())
    container = client.get_database_client(config.COSMOS_DATABASE).get_container_client(
        config.COSMOS_EVALUATION_CONTAINER
    )
    return CosmosEvaluationRuns(container)
