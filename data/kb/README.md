# RetailEase knowledge base

The RAG retrieval targets — the operational docs an investigation retrieves as evidence and
context. Authored to match the topology and scenarios so that every `expected_retrieval` (and
each historical incident's postmortem) resolves.

| Directory | Ref namespace | Resolves from |
| --- | --- | --- |
| `runbooks/` | `runbook:<id>` | `runbooks/<id>.md` |
| `architecture/` | `architecture:<id>` | `architecture/<id>.md` |
| `postmortems/` | `postmortem:<incident_id>` | `postmortems/<incident_id>-*.md` |

Every doc carries YAML frontmatter (`id`, `title`, `kind`, `services`, `source`); the `id` equals
its ref, which is how retrieval resolves. Postmortems additionally carry `incident_id` + `severity`
and correspond 1:1 to the historical incidents — that correspondence is what the known-issue fast
path and Demo 2 match against.

**Content is synthetic and Azure-native** (Container Apps revisions, Cosmos DB RU/throttling,
Service Bus dead-letter queues, Azure Cache for Redis, Azure Monitor / App Insights). The *content*
is RetailEase-specific; only document *structure* is modelled on real SRE practice (runbook shape;
danluu/post-mortems for the postmortem shape). Public references are cited in `provenance.md` (2e)
and never copied as retrieval targets.

Resolution + metadata are gated by `tests/test_kb.py`. Full cross-corpus closure lands at 2e.
