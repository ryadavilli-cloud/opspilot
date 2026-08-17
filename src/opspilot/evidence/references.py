"""The single owner of reference encoding, parsing, and resolution.

A reference travels through the system as its string form. This module is the only place that
interprets one: it decides the reference's type, splits it into parts, and answers whether it
resolves to something real. Nothing else parses a reference, keeps its own prefix list, or infers
a reference's type from the capability that produced it.

Two reference types exist, and the prefix is the declared discriminator between them. That is what
makes the one rule that matters decidable by inspection rather than by judgment: retrieved
knowledge may inform history, interpretation, and an action's provenance, and may never stand as
current operational support, because a document cannot observe the running system. Grounding reads
the type from here and needs no role field to enforce it.

Grammar, as authored in `data/answer_key/README.md`:

    logs:<service>:<event_id>
    metrics:<service or infra entity>:<metric>@<ts>
    deploys:<service>:<deploy_id>
    deps:<from>-><to>
    alert:<service>:<alert_id>
    incident:<incident_id>
    absence:<capability>:<operation_ref>
    query:<operation_ref>
    runbook:<doc_id>
    architecture:<doc_id>
    postmortem:<incident_id>

Two of the evidence forms name an operation rather than a stored row. `absence:` names an
authoritative empty result: the capability executed successfully over the recorded scope and
observed no matching item. `query:` names an aggregate answer, which is a fact about a scope and
has no underlying row to point at. Both embed an operation reference without becoming one: a bare
operation reference is still not citable, because an operation names an attempt rather than an
observation.

Parsing validates shape only. Whether a reference names something that exists is resolution, and
whether a metric timestamp lands on the corpus sample boundary is an authoring rule the answer
key's own gate enforces; neither belongs to the grammar check.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any

from opspilot import config
from opspilot.config import KB_DIR
from opspilot.data.operational_records import OperationalRecords


class ReferenceType(StrEnum):
    """What a reference names. Fixed at two; the prefix map below is the only assignment."""

    EVIDENCE = "evidence"
    KNOWLEDGE = "knowledge"


# The authoritative prefix-to-type map. No other list of prefixes exists, and a prefix absent here
# is not a reference. Adding a source means adding a row here and a resolver branch, deliberately.
PREFIX_TYPES: Mapping[str, ReferenceType] = MappingProxyType(
    {
        "logs": ReferenceType.EVIDENCE,
        "metrics": ReferenceType.EVIDENCE,
        "deploys": ReferenceType.EVIDENCE,
        "deps": ReferenceType.EVIDENCE,
        "alert": ReferenceType.EVIDENCE,
        "incident": ReferenceType.EVIDENCE,
        "absence": ReferenceType.EVIDENCE,
        "query": ReferenceType.EVIDENCE,
        "runbook": ReferenceType.KNOWLEDGE,
        "architecture": ReferenceType.KNOWLEDGE,
        "postmortem": ReferenceType.KNOWLEDGE,
    }
)

# `past_incident:` named the same document as `postmortem:` and is retired. It is called out
# separately so the old runtime's spelling fails with the reason rather than as "unknown".
RETIRED_PREFIXES: Mapping[str, str] = MappingProxyType({"past_incident": "postmortem"})

# The two evidence forms with no stored row behind them, by definition: one names a scope that
# contained nothing, the other an aggregate over a scope. Both resolve against what admission
# recorded in this investigation rather than against a source.
_OPERATION_BACKED = frozenset({"absence", "query"})

_KNOWLEDGE_DIRS: Mapping[str, str] = MappingProxyType(
    {"runbook": "runbooks", "architecture": "architecture", "postmortem": "postmortems"}
)


class ReferenceError(ValueError):
    """A string that is not a well-formed reference. Raised by the parser, never swallowed into a
    default: a reference nothing can interpret must not travel on as though it were valid."""


@dataclass(frozen=True)
class Reference:
    """A parsed reference. `raw` stays the canonical travelling form; everything else is derived.

    `entities` carries the service or infra entities the reference names, which is how a caller
    asks "what does this observation concern" without re-splitting the string. Knowledge
    references name no entity, and that is correct rather than a gap: a runbook cannot be a cause.
    """

    raw: str
    prefix: str
    reference_type: ReferenceType
    entities: tuple[str, ...] = ()
    identifier: str | None = None
    metric: str | None = None
    observed_at: datetime | None = None
    # Only an `absence:` reference names one: the capability whose empty answer was admitted.
    capability: str | None = None

    @property
    def is_evidence(self) -> bool:
        return self.reference_type is ReferenceType.EVIDENCE

    @property
    def is_knowledge(self) -> bool:
        return self.reference_type is ReferenceType.KNOWLEDGE


def reference_type_of(raw: str) -> ReferenceType:
    """The reference type, for callers that need only the classification."""
    return parse(raw).reference_type


def _require(condition: bool, raw: str, why: str) -> None:
    if not condition:
        raise ReferenceError(f"malformed reference {raw!r}: {why}")


def _parse_timestamp(raw: str, text: str) -> datetime:
    _require(text.endswith("Z"), raw, "metric timestamp must be UTC and end with Z")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReferenceError(f"malformed reference {raw!r}: unparseable timestamp") from exc
    return parsed.astimezone(UTC)


def parse(raw: str) -> Reference:
    """Parse a reference string, or raise `ReferenceError`.

    Shape only. Existence is the resolver's question, and the two are kept apart so a well-formed
    reference to a deleted row reports as unresolved rather than as malformed.
    """
    text = (raw or "").strip()
    _require(bool(text), raw, "empty")

    prefix, separator, rest = text.partition(":")
    _require(bool(separator), text, "no prefix separator")
    _require(bool(rest), text, "no body after the prefix")

    if prefix in RETIRED_PREFIXES:
        raise ReferenceError(
            f"malformed reference {text!r}: prefix {prefix!r} is retired; "
            f"use {RETIRED_PREFIXES[prefix]!r}"
        )

    reference_type = PREFIX_TYPES.get(prefix)
    if reference_type is None:
        raise ReferenceError(f"malformed reference {text!r}: unknown prefix {prefix!r}")

    if prefix == "deps":
        left, arrow, right = rest.partition("->")
        _require(bool(arrow), text, "dependency reference needs '->'")
        source, target = left.strip(), right.strip()
        _require(bool(source) and bool(target), text, "dependency endpoint is empty")
        return Reference(text, prefix, reference_type, entities=(source, target))

    if prefix == "metrics":
        entity, separator, remainder = rest.partition(":")
        _require(bool(separator), text, "metric reference needs an entity and a metric")
        metric, at, timestamp = remainder.partition("@")
        _require(bool(at), text, "metric reference needs '@<ts>'")
        _require(bool(entity.strip()) and bool(metric.strip()), text, "empty entity or metric")
        return Reference(
            text,
            prefix,
            reference_type,
            entities=(entity.strip(),),
            metric=metric.strip(),
            observed_at=_parse_timestamp(text, timestamp.strip()),
        )

    if prefix in ("logs", "deploys", "alert"):
        entity, separator, identifier = rest.partition(":")
        _require(bool(separator), text, f"{prefix} reference needs a service and an identifier")
        _require(bool(entity.strip()) and bool(identifier.strip()), text, "empty service or id")
        _require(":" not in identifier, text, f"{prefix} reference carries one identifier")
        return Reference(
            text, prefix, reference_type, entities=(entity.strip(),), identifier=identifier.strip()
        )

    if prefix == "absence":
        capability, separator, operation_ref = rest.partition(":")
        _require(bool(separator), text, "absence reference needs a capability and an operation")
        _require(
            bool(capability.strip()) and bool(operation_ref.strip()),
            text,
            "empty capability or operation reference",
        )
        _require(":" not in operation_ref, text, "absence reference carries one operation")
        return Reference(
            text,
            prefix,
            reference_type,
            identifier=operation_ref.strip(),
            capability=capability.strip(),
        )

    # What is left names one thing by its own identifier: the incident record, the operation behind
    # an aggregate, or one knowledge document. None of them names an entity.
    _require(":" not in rest, text, f"{prefix} reference carries one identifier")
    return Reference(text, prefix, reference_type, identifier=rest.strip())


def try_parse(raw: str) -> Reference | None:
    """`parse`, returning None instead of raising. For filtering a mixed list."""
    try:
        return parse(raw)
    except ReferenceError:
        return None


def entities_named(refs: object) -> set[str]:
    """Every service or infra entity named by a collection of references.

    Unparseable and knowledge references contribute nothing, which is the correct reading: a
    document names no entity, so it can never supply one.
    """
    found: set[str] = set()
    for ref in refs if isinstance(refs, (list, tuple, set, frozenset)) else []:
        parsed = try_parse(str(ref))
        if parsed is not None:
            found.update(parsed.entities)
    return found


class ReferenceResolver:
    """Resolves references against the sources the capabilities already read.

    Evidence references resolve against the operational-records container; knowledge references
    against the knowledge base on disk. The two live together because a caller resolving a citation
    should not have to know which kind it holds.

    The answer is whether the reference names something real, and nothing else. A caller that needs
    the record itself already holds it, because a reference only ever travels beside the evidence
    it was assigned to.

    A reference names its own entity, so every read here is scoped to that entity's partition
    rather than sweeping the container. What is read is cached per entity for the resolver's life,
    because resolving a brief's citations asks about the same few services repeatedly. Each read
    carries the deadline the resolver was given, like any other source call.

    The two operation-backed forms have no source row by definition: one names a scope that
    contained nothing, the other an aggregate over a scope. They resolve against the admitted
    observations passed in at construction, so this stays one resolver rather than two. Searching
    the container for them would ask a source to produce the row whose absence is the finding.
    """

    def __init__(
        self,
        records: OperationalRecords,
        kb_dir: Path | str | None = None,
        *,
        deadline_s: float | None = None,
        observations: Iterable[Any] = (),
    ) -> None:
        self._records = records
        # Indexed by the reference admission assigned. Duck-typed rather than importing the
        # admission contract, which imports this module.
        self._admitted: set[str] = {str(getattr(obs, "evidence_ref", "")) for obs in observations}
        self._kb_dir = Path(kb_dir) if kb_dir is not None else KB_DIR
        self._deadline_s = deadline_s if deadline_s is not None else config.SOURCE_DEADLINE_SECONDS
        self._logs: dict[str, set[str]] = {}
        self._deploys: dict[str, set[str]] = {}
        self._alerts: dict[str, set[str]] = {}
        self._incidents: dict[str, bool] = {}
        self._edges: set[tuple[str, str]] | None = None
        self._metric_entities: dict[str, dict[str, list[dict[str, Any]]]] = {}

    # --- lazy, entity-scoped indexes over the container ---------------------------------------
    def _log_index(self, service: str) -> set[str]:
        if service not in self._logs:
            rows = self._records.logs(service, deadline_s=self._deadline_s)
            self._logs[service] = {str(row.get("event_id", "")) for row in rows}
        return self._logs[service]

    def _deploy_index(self, service: str) -> set[str]:
        if service not in self._deploys:
            rows = self._records.deployments([service], deadline_s=self._deadline_s)
            self._deploys[service] = {str(row.get("deploy_id", "")) for row in rows}
        return self._deploys[service]

    def _alert_index(self, service: str) -> set[str]:
        if service not in self._alerts:
            rows = self._records.alerts(service, deadline_s=self._deadline_s)
            self._alerts[service] = {str(row.get("alert_id", "")) for row in rows}
        return self._alerts[service]

    def _incident_exists(self, incident_id: str) -> bool:
        if incident_id not in self._incidents:
            row = self._records.incident(incident_id, deadline_s=self._deadline_s)
            self._incidents[incident_id] = row is not None
        return self._incidents[incident_id]

    def _edge_index(self) -> set[tuple[str, str]]:
        if self._edges is None:
            edges = self._records.edges(deadline_s=self._deadline_s)
            self._edges = {(edge.get("from", ""), edge.get("to", "")) for edge in edges}
        return self._edges

    def _metric_index(self, entity: str) -> dict[str, list[dict[str, Any]]]:
        if entity not in self._metric_entities:
            index: dict[str, list[dict[str, Any]]] = {}
            for series in self._records.metric_series(entity, deadline_s=self._deadline_s):
                index.setdefault(series.get("metric", ""), []).append(series)
            self._metric_entities[entity] = index
        return self._metric_entities[entity]

    # --- resolution ---------------------------------------------------------------------------
    def _resolve_metric(self, ref: Reference) -> bool:
        entity = ref.entities[0] if ref.entities else ""
        for series in self._metric_index(entity).get(ref.metric or "", []):
            for sample in series.get("samples", []):
                stamp = sample.get("ts")
                if stamp is None:
                    continue
                parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
                if parsed.astimezone(UTC) == ref.observed_at:
                    return True
        return False

    def _resolve_knowledge(self, ref: Reference) -> bool:
        directory = self._kb_dir / _KNOWLEDGE_DIRS[ref.prefix]
        identifier = ref.identifier or ""
        if (directory / f"{identifier}.md").exists():
            return True
        # A postmortem is filed as `<incident_id>-<slug>.md`, so its reference resolves by prefix.
        return bool(identifier and sorted(directory.glob(f"{identifier}-*.md")))

    def resolves(self, raw: str | Reference) -> bool:
        """Whether a reference names something real. A malformed reference does not, by definition,
        and a well-formed one naming nothing is unresolved rather than an error."""
        try:
            ref = raw if isinstance(raw, Reference) else parse(raw)
        except ReferenceError:
            return False

        if ref.reference_type is ReferenceType.KNOWLEDGE:
            return self._resolve_knowledge(ref)
        if ref.prefix in _OPERATION_BACKED:
            return ref.raw in self._admitted
        if ref.prefix == "logs":
            return (ref.identifier or "") in self._log_index(ref.entities[0])
        if ref.prefix == "deploys":
            return (ref.identifier or "") in self._deploy_index(ref.entities[0])
        if ref.prefix == "alert":
            return (ref.identifier or "") in self._alert_index(ref.entities[0])
        if ref.prefix == "incident":
            return self._incident_exists(ref.identifier or "")
        if ref.prefix == "deps":
            return (ref.entities[0], ref.entities[1]) in self._edge_index()
        return self._resolve_metric(ref)
