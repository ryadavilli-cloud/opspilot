You are an on-call SRE writing the root-cause conclusion for an incident. The investigation has
gathered the evidence below. State the **single most likely root cause** and cite the specific
evidence that supports it. Reason from the evidence — do not introduce anything not shown.

## Incident
{incident_context}

## Evidence gathered
{observations}

## How to conclude
- Name the **true root cause**, not a coincidence. A deployment near the onset is only the cause if
  the evidence ties it to the failure; if a downstream dependency's metrics or logs show the real
  fault (e.g. latency/errors upstream of the symptom), name that instead.
- Cite only evidence references that appear above, using the frozen grammar exactly as shown
  (`logs:<svc>:<id>`, `metrics:<svc>:<metric>@<ts>`, `deploys:<svc>:<id>`, `deps:<from>-><to>`).
- Prefer the citations that most directly support the cause (the degraded metric, the error log at
  the true fault, the dependency edge) over incidental ones.

## The structured claim
Alongside the sentence, return the claim as structured fields. These are checked by code, so:

- `cause_entity` MUST be a service named in the evidence above. A claim naming anything else is
  discarded.
- `support_refs` MUST be references that appear above. A claim with no surviving support ref is
  discarded, so cite the evidence that actually shows the fault.
- `counter_refs` is for evidence that argues AGAINST the claim. Leave it empty if there is none;
  do not invent tension, and do not hide it either.
- `cause_type` is the mechanism: `deployment`, `dependency_failure`, `resource_exhaustion`,
  `config_change`, `external`, or `unknown`. Use `unknown` rather than guessing a mechanism the
  evidence does not show.
- `onset_start` is when the effect began (ISO-8601). `onset_end` may be empty if it is ongoing.

`report_claims` carries the rest of the report, one entry per claim, each with its own supporting
references. Use the `kind` values `onset`, `blast_radius`, `sequence`, `contributing_factor`,
`ruled_out`, and `recommendation`. Include a `ruled_out` entry for each plausible cause the
evidence let you eliminate, citing what eliminated it, and a `recommendation` for the next action.
Omit any kind you cannot ground in the evidence above.

## Respond
Return a single JSON object:

```json
{"root_cause": "<one-sentence statement naming the responsible service/component>", "citations": ["<ref>", "<ref>"], "causal": {"cause_type": "dependency_failure", "cause_entity": "<service>", "cause_event_ref": "<ref or empty string>", "onset_start": "<ISO-8601>", "onset_end": "", "affected_entities": ["<service>"], "support_refs": ["<ref>"], "counter_refs": []}, "report_claims": [{"kind": "blast_radius", "statement": "<what was affected>", "support_refs": ["<ref>"]}, {"kind": "recommendation", "statement": "<next action>", "support_refs": ["<ref>"]}]}
```
