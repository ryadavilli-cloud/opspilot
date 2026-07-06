# RetailEase answer key

The source of truth for OpsPilot's incident corpus. Everything else in `data/` and the eval
golden sets is **derived from or validated against** these two files:

| File | What it is |
| --- | --- |
| `topology.yaml` | The RetailEase service/infra/external graph and its dependency edges — the spine. |
| `scenarios.yaml` | Six incident scenarios authored as structured specs — the labels. |
| `build_goldens.py` | Deterministic projection of the above into `eval/golden_*.json`. |

```
topology + scenarios  ──build_goldens.py──▶  eval/golden_incidents.json
   (hand-authored)                           eval/golden_retrieval.json   (generated)
```

The golden JSON is **generated, never hand-edited.** `tests/test_answer_key.py` regenerates it
in memory and fails if the committed files drift. After editing the answer key, run:

```
python data/answer_key/build_goldens.py
```

## The reference grammar (cross-phase contract)

Refs are self-describing: the prefix names the source, so a resolver can dispatch on it. The
evidence half matches the **frozen `Evidence.source` set** in `src/opspilot/state.py`, so the
Phase 3 tools conform to these refs rather than the reverse.

### Evidence refs — what tools surface (`evidence[].ref`)

| source | grammar | example |
| --- | --- | --- |
| `logs` | `logs:<service>:<event_id>` | `logs:payment-api:evt-001-01` |
| `metrics` | `metrics:<service\|infra>:<metric>@<ts>` | `metrics:checkout-api:http_5xx_rate@2026-06-28T10:15:00Z` |
| `deploys` | `deploys:<service>:<deploy_id>` | `deploys:payment-api:dep-20260512-01` |
| `deps` | `deps:<from>-><to>` | `deps:checkout-api->payment-api` |

`<ts>` is UTC `...Z` and must land on a 5-minute sample boundary (see
`metric_sample_interval_minutes` in `topology.yaml`). `deps` refs must be a real edge.

### Retrieval ids — KB docs the RAG should return (`expected_retrieval`)

| namespace | grammar | resolves to (Phase 2d) |
| --- | --- | --- |
| `runbook` | `runbook:<doc_id>` | `data/kb/runbooks/<doc_id>.md` |
| `architecture` | `architecture:<doc_id>` | `data/kb/architecture/<doc_id>.md` |
| `postmortem` | `postmortem:<incident_id>` | `data/kb/postmortems/<incident_id>-*.md` |

A retrieved runbook cites as evidence `source=runbook`; a retrieved postmortem cites as
`source=past_incident` (`past_incident:<incident_id>`). Architecture docs orient the agent but
are not themselves cited as evidence.

## Scenario invariants (enforced by the test)

- 6 scenarios: 3 `historical` + 3 `novel`.
- `historical` → `expected_intent: known_issue`, `expected_match: postmortem:<own id>` (it seeds
  that postmortem and the Phase 9.5 fast path should match it).
- `novel` → `expected_intent: novel_investigation`, `expected_match: null`.
- Every evidence/retrieval ref obeys the grammar above and points at a real topology entity.
- `red_herring` (when present) is also listed in `expected_evidence` — it exists in telemetry and
  must be ruled out, not omitted. Used by `inc-004` (Demo 1) where the recent deploy is innocent.

## What is *not* checked yet

Full closure — every evidence ref resolving to a generated telemetry row, every retrieval id to a
real KB doc — is **Phase 2e**, once 2b telemetry and 2d KB exist. Until then the test guards the
answer key's internal coherence and its sync with the goldens.

## Demo mapping

| Scenario | Role |
| --- | --- |
| `inc-004` | Demo 1 — novel investigation with a red-herring deploy. |
| `inc-003` | Demo 2 — known-issue repeat; an incoming Service Bus backlog matches this postmortem. |

## Provenance

Pure-synthetic RetailEase. No employer or customer data. Public datasets (loghub,
danluu/post-mortems, synthetic-servicenow-incidents) are authoring *reference* only and are not
mixed into this answer key; any later use is a separate corpus, cited in `data/provenance.md` (2e).
