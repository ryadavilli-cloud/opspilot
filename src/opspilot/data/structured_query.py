"""The bounded query structure, the surface it may address, and its translation.

The model does not emit query text. It emits a structure whose every part is drawn from the
approved surface, and that structure is what validation checks and what execution translates.
Nothing here accepts text from a caller: an unapproved field or an
unsupported operation has no expressible form rather than being caught after the fact.

Translation is the one place a query string exists, and it is assembled from this module's own
constants. Field names reach the text only after being looked up in `APPROVED_SURFACE`, so a name
a caller supplied can never appear in it; every value travels as a parameter. That is what makes
"no unapproved read surface is reachable" a property of the shape rather than of escaping.

What has no representation here has no representation anywhere: grouping, ordering, joins, writes,
subqueries, free-text fragments, and every aggregate but a count. They are absent from the
structure rather than rejected by a rule, which is the difference between unsupported and
forbidden-but-expressible.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from opspilot import config


class FieldType(StrEnum):
    """What a field holds, which is what decides whether a predicate value fits it."""

    TEXT = "text"
    NUMBER = "number"
    BOOLEAN = "boolean"
    TIMESTAMP = "timestamp"


# The approved surface: one entry per collection, one type per field. An explicit static mapping,
# like the capability registry, so a collection or field is reachable by being written here and by
# no other means.
#
# Narrower than the stored record on purpose. `incident.root_cause`, `incident.resolution`,
# `incident.close_code`, and `deployment.note` are the corpus's own answer text, and this is the
# one path where a model chooses its own projection. A tabular question needs none of them, so
# they are absent from the surface rather than trusted not to be asked for. Free-text description
# and title fields are absent for the same reason and because reading prose is what the passage
# path is for.
APPROVED_SURFACE: Mapping[str, Mapping[str, FieldType]] = MappingProxyType(
    {
        "incident": MappingProxyType(
            {
                "incident_id": FieldType.TEXT,
                "number": FieldType.TEXT,
                "category": FieldType.TEXT,
                "priority": FieldType.TEXT,
                "impact": FieldType.TEXT,
                "urgency": FieldType.TEXT,
                "state": FieldType.TEXT,
                "opened_at": FieldType.TIMESTAMP,
                "resolved_at": FieldType.TIMESTAMP,
                "made_sla": FieldType.BOOLEAN,
                "reassignment_count": FieldType.NUMBER,
                "is_known_error": FieldType.BOOLEAN,
            }
        ),
        "deployment": MappingProxyType(
            {
                "deploy_id": FieldType.TEXT,
                "service": FieldType.TEXT,
                "ts": FieldType.TIMESTAMP,
                "version": FieldType.TEXT,
            }
        ),
        "alert": MappingProxyType(
            {
                "alert_id": FieldType.TEXT,
                "incident_id": FieldType.TEXT,
                "service": FieldType.TEXT,
                "severity": FieldType.TEXT,
                "role": FieldType.TEXT,
                "signal": FieldType.TEXT,
                "is_trigger": FieldType.BOOLEAN,
                "fired_at": FieldType.TIMESTAMP,
            }
        ),
    }
)


class PredicateOp(StrEnum):
    """The supported predicate forms, and nothing else.

    Equality and inequality, membership in a supplied set, a bounded range, and presence or
    absence. Membership is also how disjunction is expressed, which is why no OR group exists:
    the design permits disjunction within one field only, and a set does exactly that.
    """

    EQ = "eq"
    NE = "ne"
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"
    IN = "in"
    BETWEEN = "between"
    PRESENT = "present"
    ABSENT = "absent"


_COMPARISONS: Mapping[PredicateOp, str] = MappingProxyType(
    {
        PredicateOp.EQ: "=",
        PredicateOp.NE: "!=",
        PredicateOp.LT: "<",
        PredicateOp.LTE: "<=",
        PredicateOp.GT: ">",
        PredicateOp.GTE: ">=",
    }
)

# Operations a field of this type cannot carry. A range over a boolean is not a narrower query,
# it is a malformed one, and the same is true of an ordering comparison on a free-text label.
_ORDERED_TYPES = frozenset({FieldType.NUMBER, FieldType.TIMESTAMP})


class QueryRejected(ValueError):
    """A structure that will not be executed, and why, in caller-safe terms.

    Raised before anything reaches the source. A rejected query produces a limitation rather than
    an empty result, so the question it failed to answer stays open instead of reading as an
    authoritative absence.
    """


class Predicate(BaseModel):
    """One narrowing condition. Predicates combine with conjunction and nothing else."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str
    op: PredicateOp
    value: Any = None
    values: list[Any] = Field(default_factory=list)
    low: Any = None
    high: Any = None

    @model_validator(mode="after")
    def _operands_match_the_operation(self) -> Predicate:
        if self.op is PredicateOp.IN:
            if not self.values:
                raise ValueError("a membership predicate needs a non-empty set")
        elif self.op is PredicateOp.BETWEEN:
            if self.low is None or self.high is None:
                raise ValueError("a range predicate needs both bounds")
        elif self.op in (PredicateOp.PRESENT, PredicateOp.ABSENT):
            if self.value is not None or self.values:
                raise ValueError("a presence predicate takes no operand")
        elif self.value is None:
            raise ValueError(f"the {self.op} predicate needs a value")
        return self


class StructuredQuery(BaseModel):
    """One query over one approved collection.

    A projection or the count form, never both and never neither: a query that asked for nothing
    would have no result to normalize, and one that asked for both would have two.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    collection: str
    predicates: list[Predicate] = Field(default_factory=list)
    projection: list[str] = Field(default_factory=list)
    aggregate: Literal["count"] | None = None
    limit: int = Field(gt=0)

    @model_validator(mode="after")
    def _exactly_one_result_form(self) -> StructuredQuery:
        if bool(self.projection) == bool(self.aggregate):
            raise ValueError("a query names either a projection or the count form, not both")
        if self.limit > config.STRUCTURED_QUERY_MAX_LIMIT:
            raise ValueError(f"limit exceeds the ceiling of {config.STRUCTURED_QUERY_MAX_LIMIT}")
        return self


def _fits(value: Any, field_type: FieldType) -> bool:
    if field_type is FieldType.BOOLEAN:
        return isinstance(value, bool)
    if field_type is FieldType.NUMBER:
        # bool is an int in Python, and a boolean is not a number here.
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if field_type is FieldType.TIMESTAMP:
        if not isinstance(value, str):
            return False
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
        return True
    return isinstance(value, str)


def validate(query: StructuredQuery, granted: frozenset[str] | None = None) -> None:
    """Check the structure against the approved surface and the grant, before anything executes.

    `granted` is the set of collections this request was allowed, which may be narrower than the
    approved surface. A structure that is well formed and addresses an approved collection the
    request was not granted is still refused, because being expressible is not the same as being
    permitted here.
    """
    fields = APPROVED_SURFACE.get(query.collection)
    if fields is None:
        raise QueryRejected(f"collection {query.collection!r} is not on the approved surface")
    if granted is not None and query.collection not in granted:
        raise QueryRejected(f"collection {query.collection!r} was not granted to this request")

    for name in query.projection:
        if name not in fields:
            raise QueryRejected(
                f"field {name!r} is not on the approved surface for this collection"
            )

    for predicate in query.predicates:
        field_type = fields.get(predicate.field)
        if field_type is None:
            raise QueryRejected(
                f"field {predicate.field!r} is not on the approved surface for this collection"
            )
        if predicate.op in (PredicateOp.PRESENT, PredicateOp.ABSENT):
            continue
        if predicate.op is PredicateOp.BETWEEN:
            if field_type not in _ORDERED_TYPES:
                raise QueryRejected(f"a range is not an operation on a {field_type} field")
            operands = [predicate.low, predicate.high]
        elif predicate.op is PredicateOp.IN:
            operands = list(predicate.values)
        else:
            ordered_only = predicate.op not in (PredicateOp.EQ, PredicateOp.NE)
            if ordered_only and field_type not in _ORDERED_TYPES:
                raise QueryRejected(f"{predicate.op} is not an operation on a {field_type} field")
            operands = [predicate.value]
        for operand in operands:
            if not _fits(operand, field_type):
                raise QueryRejected(
                    f"value for {predicate.field!r} does not match its {field_type} type"
                )


def translate(query: StructuredQuery) -> tuple[str, list[dict[str, Any]]]:
    """Turn a validated structure into one parameterized, read-only Cosmos read.

    Call `validate` first. Every identifier written here is read back out of `APPROVED_SURFACE`
    rather than taken from the structure, so no caller-supplied string reaches the text, and every
    value is bound as a parameter. `kind` scopes the read to the collection's partition.
    """
    fields = APPROVED_SURFACE[query.collection]

    def approved(name: str) -> str:
        """The identifier as this module spells it, not as the caller spelled it.

        Both strings compare equal, and only this one came from `APPROVED_SURFACE`. Writing the
        looked-up key into the text is what keeps a caller-supplied string out of it, so a field
        name is never a place a fragment could be smuggled in. `validate` has already established
        that the key is present; a missing one here is a caller that skipped it.
        """
        canonical = next((key for key in fields if key == name), None)
        if canonical is None:
            raise QueryRejected(
                f"field {name!r} is not on the approved surface for this collection"
            )
        return canonical

    parameters: list[dict[str, Any]] = [{"name": "@kind", "value": query.collection}]
    conditions = ["c.kind = @kind"]

    for index, predicate in enumerate(query.predicates):
        name = approved(predicate.field)
        if predicate.op is PredicateOp.PRESENT:
            conditions.append(f"(IS_DEFINED(c.{name}) AND NOT IS_NULL(c.{name}))")
        elif predicate.op is PredicateOp.ABSENT:
            conditions.append(f"(NOT IS_DEFINED(c.{name}) OR IS_NULL(c.{name}))")
        elif predicate.op is PredicateOp.IN:
            parameters.append({"name": f"@p{index}", "value": list(predicate.values)})
            conditions.append(f"ARRAY_CONTAINS(@p{index}, c.{name})")
        elif predicate.op is PredicateOp.BETWEEN:
            parameters.append({"name": f"@p{index}lo", "value": predicate.low})
            parameters.append({"name": f"@p{index}hi", "value": predicate.high})
            conditions.append(f"(c.{name} >= @p{index}lo AND c.{name} <= @p{index}hi)")
        else:
            parameters.append({"name": f"@p{index}", "value": predicate.value})
            conditions.append(f"c.{name} {_COMPARISONS[predicate.op]} @p{index}")

    where = " AND ".join(conditions)
    if query.aggregate == "count":
        # No TOP here, and not by oversight. A count returns one value rather than rows, so there
        # is nothing for a row limit to bound, and Cosmos rejects every form that tries to impose
        # one: a counted subquery, aliased or not, projecting a literal or a field, and the
        # OFFSET/LIMIT variant are all BadRequest. Established against the live container, because
        # a query this module only ever asserted against itself would have looked correct.
        #
        # The limit stays mandatory in the structure: it is what the structure guarantees, and a
        # query may not omit it. What bounds the work this form does is the deadline every read on
        # this path carries.
        return f"SELECT VALUE COUNT(1) FROM c WHERE {where}", parameters

    projected = ", ".join(f"c.{approved(name)}" for name in query.projection)
    return f"SELECT TOP {query.limit} {projected} FROM c WHERE {where}", parameters
