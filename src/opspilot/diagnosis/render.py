"""Rendering: report prose is DERIVED from the typed claim, never authored alongside it.

`Claim.statement` used to be documented as "human-readable, never parsed", which was a loophole:
the deterministic checks validated the structure, the human read the prose, and nothing forced
them to agree. A report could carry `cause_entity="payment-gateway"` while its sentence blamed a
checkout deploy: the gate passing a structure the human never sees, the human approving prose the
gate never checked.

So the sentence is template substitution over the structured fields. There is no path by which the
prose can name an entity the claim does not, because the entity is only ever interpolated from
`claim.cause_entity`. When the single-authority refactor lands at 6b this moves into a dedicated
`render_report` node; the templates themselves do not change.
"""

from __future__ import annotations

from opspilot.diagnosis.contracts import CausalClaim, ReportClaim

# One clause per mechanism. `{entity}` is always `claim.cause_entity`, so no template can blame
# anything else; a new `cause_type` member without a clause falls back to the generic wording
# rather than silently rendering an empty or misleading sentence.
_CAUSE_CLAUSE: dict[str, str] = {
    "deployment": "a deployment of {entity}",
    "dependency_failure": "a failure in the dependency {entity}",
    "resource_exhaustion": "resource exhaustion in {entity}",
    "config_change": "a configuration change to {entity}",
    "external": "an external fault affecting {entity}",
    "unknown": "an unclassified fault in {entity}",
}

_CLAIM_PREFIX: dict[str, str] = {
    "onset": "Onset",
    "blast_radius": "Blast radius",
    "sequence": "Sequence",
    "contributing_factor": "Contributing factor",
    "ruled_out": "Ruled out",
    "recommendation": "Recommendation",
}


def render_causal_statement(claim: CausalClaim) -> str:
    """The root-cause sentence, built only from the claim's own fields."""
    clause = _CAUSE_CLAUSE.get(claim.cause_type, _CAUSE_CLAUSE["unknown"])
    sentence = f"Root cause: {clause.format(entity=claim.cause_entity)}"

    affected = [e for e in claim.affected_entities if e != claim.cause_entity]
    if affected:
        sentence += f", affecting {', '.join(sorted(affected))}"
    if claim.onset_window.start:
        window = claim.onset_window.start
        if claim.onset_window.end:
            window += f" to {claim.onset_window.end}"
        sentence += f", with effect onset at {window}"
    if claim.cause_event_ref:
        sentence += f" (causing event {claim.cause_event_ref})"
    return sentence + "."


def render_report_claim_statement(claim: ReportClaim) -> str:
    """A secondary claim's sentence. The model's proposed wording is kept as the body because these
    are descriptive rather than causal, but the KIND prefix and the supporting refs are rendered
    from the structure, so the claim always displays what it is and what backs it."""
    prefix = _CLAIM_PREFIX.get(claim.kind, claim.kind.replace("_", " ").capitalize())
    body = claim.statement.strip() or "(no detail given)"
    return f"{prefix}: {body} [{', '.join(claim.support_refs)}]"
