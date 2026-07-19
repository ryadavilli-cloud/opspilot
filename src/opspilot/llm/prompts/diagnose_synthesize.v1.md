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

## Respond
Return a single JSON object:

```json
{"root_cause": "<one-sentence statement naming the responsible service/component>", "citations": ["<ref>", "<ref>"]}
```
