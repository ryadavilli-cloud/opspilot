"""The single owner of reference encoding, parsing, and resolution (D-008).

A reference travels through the system as its string form. This module is the only place that
interprets one: it decides the reference's type, splits it into parts, and answers whether it
resolves to something real. Nothing else parses a reference, keeps its own prefix list, or infers
a reference's type from the capability that produced it.

Two reference types exist, and the prefix is the declared discriminator between them
(`data-and-evidence.md` "Identity and Reference Model"). That is what makes citation-role
compatibility decidable by inspection rather than by judgment: an evidence reference may occupy
any citation role, a knowledge reference only the historical-or-contextual role, and
`role_is_admissible` is the one function that answers it.

Grammar, as authored in `data/answer_key/README.md`:

    logs:<service>:<event_id>
    metrics:<service or infra entity>:<metric>@<ts>
    deploys:<service>:<deploy_id>
    deps:<from>-><to>
    runbook:<doc_id>
    architecture:<doc_id>
    postmortem:<incident_id>

Parsing validates shape only. Whether a reference names something that exists is resolution, and
whether a metric timestamp lands on the corpus sample boundary is an authoring rule the answer
key's own gate enforces; neither belongs to the grammar check.
"""

from __future__ import annotations

from collections.abc import Mapping
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


class CitationRole(StrEnum):
    """The three citation roles. A larger vocabulary would invite relabeling, and relabeling is
    how a deterministic grounding check becomes negotiable."""

    CURRENT_SUPPORT = "current_operational_support"
    CURRENT_CONTRADICTION = "current_operational_contradiction"
    HISTORICAL_CONTEXT = "historical_or_contextual_support"


# The authoritative prefix-to-type map. No other list of prefixes exists, and a prefix absent here
# is not a reference. Adding a source means adding a row here and a resolver branch, deliberately.
PREFIX_TYPES: Mapping[str, ReferenceType] = MappingProxyType(
    {
        "logs": ReferenceType.EVIDENCE,
        "metrics": ReferenceType.EVIDENCE,
        "deploys": ReferenceType.EVIDENCE,
        "deps": ReferenceType.EVIDENCE,
        "runbook": ReferenceType.KNOWLEDGE,
        "architecture": ReferenceType.KNOWLEDGE,
        "postmortem": ReferenceType.KNOWLEDGE,
    }
)

# `past_incident:` named the same document as `postmortem:` and is retired by D-008. It is called
# out separately so the old runtime's spelling fails with the reason rather than as "unknown".
RETIRED_PREFIXES: Mapping[str, str] = MappingProxyType({"past_incident": "postmortem"})

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

    @property
    def is_evidence(self) -> bool:
        return self.reference_type is ReferenceType.EVIDENCE

    @property
    def is_knowledge(self) -> bool:
        return self.reference_type is ReferenceType.KNOWLEDGE


def role_is_admissible(reference_type: ReferenceType, role: CitationRole) -> bool:
    """Whether a reference of this type may occupy this citation role.

    Retrieved knowledge cannot carry current operational support or contradiction, because a
    document cannot observe the running system. Deciding this from the type alone is the whole
    point of the prefix map.
    """
    if reference_type is ReferenceType.EVIDENCE:
        return True
    return role is CitationRole.HISTORICAL_CONTEXT


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

    Shape only. Existence is `ReferenceResolver`'s question, and the two are kept apart so a
    well-formed reference to a deleted row reports as unresolved rather than as malformed.
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

    if prefix in ("logs", "deploys"):
        entity, separator, identifier = rest.partition(":")
        _require(bool(separator), text, f"{prefix} reference needs a service and an identifier")
        _require(bool(entity.strip()) and bool(identifier.strip()), text, "empty service or id")
        return Reference(
            text, prefix, reference_type, entities=(entity.strip(),), identifier=identifier.strip()
        )

    # Knowledge references are a single opaque document identity.
    _require(":" not in rest, text, "knowledge reference carries one identifier")
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


@dataclass(frozen=True)
class Resolution:
    """Whether a reference names something real, and what it named when it did."""

    reference: Reference
    resolved: bool
    record: Any | None = None


class ReferenceResolver:
    """Resolves references against the sources the capabilities already read.

    Evidence references resolve against the operational-records container; knowledge references
    against the knowledge base on disk. The two live together because a caller resolving a citation
    should not have to know which kind it holds.

    A reference names its own entity, so every read here is scoped to that entity's partition
    rather than sweeping the container. What is read is cached per entity for the resolver's life,
    because resolving a brief's citations asks about the same few services repeatedly. Each read
    carries the deadline the resolver was given, like any other source call.
    """

    def __init__(
        self,
        records: OperationalRecords,
        kb_dir: Path | str | None = None,
        *,
        deadline_s: float | None = None,
    ) -> None:
        self._records = records
        self._kb_dir = Path(kb_dir) if kb_dir is not None else KB_DIR
        self._deadline_s = deadline_s if deadline_s is not None else config.SOURCE_DEADLINE_SECONDS
        self._logs: dict[str, dict[str, dict[str, Any]]] = {}
        self._deploys: dict[str, dict[str, dict[str, Any]]] = {}
        self._edges: set[tuple[str, str]] | None = None
        self._metric_entities: dict[str, dict[str, list[dict[str, Any]]]] = {}

    # --- lazy, entity-scoped indexes over the container ---------------------------------------
    def _log_index(self, service: str) -> dict[str, dict[str, Any]]:
        if service not in self._logs:
            rows = self._records.logs(service, deadline_s=self._deadline_s)
            self._logs[service] = {row.get("event_id", ""): row for row in rows}
        return self._logs[service]

    def _deploy_index(self, service: str) -> dict[str, dict[str, Any]]:
        if service not in self._deploys:
            rows = self._records.deployments([service], deadline_s=self._deadline_s)
            self._deploys[service] = {row.get("deploy_id", ""): row for row in rows}
        return self._deploys[service]

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
    def _resolve_metric(self, ref: Reference) -> tuple[bool, Any | None]:
        entity = ref.entities[0] if ref.entities else ""
        for series in self._metric_index(entity).get(ref.metric or "", []):
            for sample in series.get("samples", []):
                stamp = sample.get("ts")
                if stamp is None:
                    continue
                parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
                if parsed.astimezone(UTC) == ref.observed_at:
                    return True, sample
        return False, None

    def _resolve_knowledge(self, ref: Reference) -> tuple[bool, Any | None]:
        directory = self._kb_dir / _KNOWLEDGE_DIRS[ref.prefix]
        identifier = ref.identifier or ""
        exact = directory / f"{identifier}.md"
        if exact.exists():
            return True, exact
        # A postmortem is filed as `<incident_id>-<slug>.md`, so its reference resolves by prefix.
        matches = sorted(directory.glob(f"{identifier}-*.md")) if identifier else []
        return (True, matches[0]) if matches else (False, None)

    def resolve(self, raw: str | Reference) -> Resolution:
        """Resolve one reference. A malformed string raises; a well-formed one that names nothing
        returns `resolved=False`."""
        ref = raw if isinstance(raw, Reference) else parse(raw)

        if ref.reference_type is ReferenceType.KNOWLEDGE:
            found, record = self._resolve_knowledge(ref)
        elif ref.prefix == "logs":
            record = self._log_index(ref.entities[0]).get(ref.identifier or "")
            found = record is not None
        elif ref.prefix == "deploys":
            record = self._deploy_index(ref.entities[0]).get(ref.identifier or "")
            found = record is not None
        elif ref.prefix == "deps":
            edge = (ref.entities[0], ref.entities[1])
            found = edge in self._edge_index()
            record = edge if found else None
        else:
            found, record = self._resolve_metric(ref)

        return Resolution(reference=ref, resolved=found, record=record)

    def resolves(self, raw: str) -> bool:
        """Whether a reference resolves. A malformed reference does not resolve, by definition."""
        try:
            return self.resolve(raw).resolved
        except ReferenceError:
            return False
