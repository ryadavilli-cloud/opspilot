"""A stand-in for the `operational-records` container, and the seeded readers built on it.

The container object is injected into `OperationalRecords`, so a test holds this and the deployed
path holds a real Cosmos container. There is one implementation of every query; only the thing
being queried differs.

`FakeContainer` answers by interpreting the parameters, not by parsing the query text. Every
authored query narrows on `c.<field> = @<field>` or `ARRAY_CONTAINS(@<field>s, c.<field>)`, so the
parameter name is the field and a list value means membership. That is the convention
`operational_records.py` writes to, and it is small enough to read in one sitting; a fake that
parsed SQL would be a second query engine, and one that matched query strings would break on
whitespace.

Every call's `timeout` is recorded, because "the deadline reached the source" is only assertable
where the source can be asked what it was given.
"""

from __future__ import annotations

import functools
import importlib.util
import sys
from pathlib import Path
from typing import Any

from opspilot.data.operational_records import OperationalRecords

_REPO_ROOT = Path(__file__).resolve().parents[1]


@functools.cache
def _preparation():
    """`scripts/prepare_corpus.py`, imported by path the way the answer key's generator is.

    The corpus files are shaped into container documents by preparation and by nothing else, so a
    fixture that reshaped them itself would be asserting against a second, unowned shaping.
    """
    spec = importlib.util.spec_from_file_location(
        "opspilot_prepare_corpus", _REPO_ROOT / "scripts" / "prepare_corpus.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ContainerUnreachable(RuntimeError):
    """What a container raises when it cannot answer at all."""


class UnrecognizedQuery(AssertionError):
    """A query shape this fake was not built to answer.

    Raised rather than returning nothing. A fake that answers an unfamiliar query with an empty
    result does not fail; it removes the assertion, and the test goes on passing for a reason
    unrelated to the behavior it claims to protect. Failing here says which query arrived.
    """


class CannedContainer:
    """A container that ignores the query entirely and returns what it was given.

    For asserting the one thing that does not depend on filtering: how a provider outcome becomes
    the two axes. Rows mean `succeeded`, nothing means `succeeded` with `empty`, and raising means
    `unavailable`. What the query said is irrelevant to that mapping, so this deliberately does not
    read it, and cannot be mistaken for evidence that a query filtered correctly.
    """

    def __init__(self, rows: list[Any] | None = None, *, unreachable: bool = False) -> None:
        self.rows = rows if rows is not None else []
        self.unreachable = unreachable
        self.timeouts: list[float] = []
        self.queries: list[str] = []

    def query_items(self, query: str, parameters=None, timeout: float | None = None, **_: Any):
        self.queries.append(query)
        self.timeouts.append(timeout)  # type: ignore[arg-type]
        if self.unreachable:
            raise ContainerUnreachable("the container refused the connection")
        return list(self.rows)


class FakeContainer:
    """Enough of a Cosmos container to answer the authored queries.

    `unreachable=True` makes every read raise, which is how "the source did not answer" is told
    apart from "the source answered with nothing".
    """

    def __init__(self, documents: list[dict[str, Any]], *, unreachable: bool = False) -> None:
        self.documents = documents
        self.unreachable = unreachable
        self.timeouts: list[float] = []
        self.queries: list[str] = []
        # Every field any document carries, plus the partition key. What is not here is a
        # parameter this fake cannot interpret, and it says so rather than matching nothing.
        self._known_fields = {key for document in documents for key in document} | {"kind"}

    def query_items(
        self,
        query: str,
        parameters: list[dict[str, Any]] | None = None,
        enable_cross_partition_query: bool = False,
        timeout: float | None = None,
        **_: Any,
    ) -> list[Any]:
        self.queries.append(query)
        # Recorded before the unreachable branch: a call that failed still carried a deadline, and
        # a bound that only holds on the happy path is not a bound.
        self.timeouts.append(timeout)  # type: ignore[arg-type]
        if self.unreachable:
            raise ContainerUnreachable("the container refused the connection")

        matched = [doc for doc in self.documents if self._matches(doc, parameters or [])]
        if "COUNT(1)" in query:
            return [len(matched)]
        return matched

    def _matches(self, document: dict[str, Any], parameters: list[dict[str, Any]]) -> bool:
        for parameter in parameters:
            field = parameter["name"].lstrip("@")
            wanted = parameter["value"]
            if isinstance(wanted, list):
                # `ARRAY_CONTAINS(@services, c.service)`: the parameter is plural, the field is
                # not, and this is the only place that convention is interpreted.
                field = field.removesuffix("s")
            if field not in self._known_fields:
                # A positional parameter, as the structured-query translator emits. This fake
                # answers the authored queries, whose parameters are named for their field; it
                # cannot evaluate a translated one and must not pretend the scope was empty.
                raise UnrecognizedQuery(
                    f"parameter {parameter['name']!r} names no field this fake can match on. "
                    "A translated structured query is not answerable here: assert its text and "
                    "parameters against `translate`, and its outcome mapping with CannedContainer."
                )
            if isinstance(wanted, list):
                if document.get(field) not in wanted:
                    return False
            elif document.get(field) != wanted:
                return False
        return True


@functools.cache
def _corpus_documents() -> tuple[dict[str, Any], ...]:
    return tuple(_preparation().operational_documents())


def corpus_documents() -> list[dict[str, Any]]:
    """Every operational record, shaped exactly as preparation writes it. Shaped once for the
    session: thirteen thousand log rows are not worth re-reading per module."""
    return list(_corpus_documents())


def corpus_container(**kwargs: Any) -> FakeContainer:
    return FakeContainer(corpus_documents(), **kwargs)


def corpus_records(**kwargs: Any) -> OperationalRecords:
    """A reader over the whole authored corpus, container-shaped. Fixture truth for the tests that
    assert against real RetailEase incidents."""
    return OperationalRecords(corpus_container(**kwargs))


def records_from(documents: list[dict[str, Any]], **kwargs: Any) -> OperationalRecords:
    """A reader over hand-built documents, for the edge cases the authored corpus does not hold."""
    return OperationalRecords(FakeContainer(documents, **kwargs))


def deployment_documents(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deployment rows as container documents: the partition fields, then the row."""
    return [{**row, "kind": "deployment", "id": row.get("deploy_id")} for row in rows]


def log_documents(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**row, "kind": "log", "id": row.get("event_id")} for row in rows]
