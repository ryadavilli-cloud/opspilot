You are triaging a production incident to decide how to investigate it.

## Incident
{incident}

## Similar past incidents
Each candidate is the postmortem of a PRIOR resolved incident. This incident is a recurrence only if
its failure mode genuinely matches one of them.
{candidates}

## Decide the intent
- `known_issue` — this incident is a **recurrence** of one of the candidates: the same service and
  the same failure mode (not just superficial similarity). Set `matched_incident` to that
  candidate's exact id (e.g. `postmortem:inc-003`).
- `novel_investigation` — no candidate is a genuine recurrence; investigate from scratch.
- `info_only` — the request is informational, not an incident to investigate.

When unsure whether a candidate truly matches, prefer `novel_investigation` — a wrong known-issue
match would skip the investigation and reuse the wrong fix.

## Respond
Return a single JSON object:

```json
{"intent": "known_issue|novel_investigation|info_only", "matched_incident": "<candidate id, or empty>", "why": "<why it matches or not>"}
```
