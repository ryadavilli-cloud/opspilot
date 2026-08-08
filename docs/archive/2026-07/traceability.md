# OpsPilot — Traceability (component → dimension → capability)

**Showcase companion to [`architecture.md`](./architecture.md).** This maps each built/target component
to the dimension it exercises and the capability it demonstrates. It is a traceability matrix for the
project, not part of the core architecture — the architecture doc references it but does not depend on
it.

| Component | Dimension | Capability |
|---|---|---|
| Event ingestion, separated ids (`investigation_id`→`thread_id`), durable checkpointer | Architecture | Distributed-systems intuition |
| Supervisor triage + router + candidate-known-issue verification | Architecture / orchestration | Multi-agent coordination |
| Hybrid retrieval (dense + BM25 + RRF + cross-encoder rerank), multi-index | Domain capability | RAG + memory |
| Retrieval passages into the reasoning context + a joining eval axis | Domain capability / testing | RAG measured end-to-end, not per-component |
| MCP tool layer + parity suite + allowlist (v2) | Architecture / security | MCP, tool boundary design |
| Subagents-as-tools / subgraphs | Architecture / domain | Context engineering |
| Agentic diagnosis loop + sufficiency gate + red-herring discrimination | Architecture | Agentic reasoning, when-to-stop, correlation vs causation |
| Deterministic contradiction detector + severity re-evaluation | Architecture / grounding | Stop rules that test coherence, not volume; rigor tracking discovered risk |
| Gateway-attested grounding set (tool ledger + opaque handles) + evidence-manifest hash binding | Security / grounding | Guardrails as trusted-writer derivations, not conventions or fields |
| HITL interrupt + approval-hash binding + edit-revalidation | Security / grounding | Escalation + audit, publication control |
| Pause→decide→resume as a three-request protocol (identity, concurrency, durability) | Architecture | Long-running distributed workflow design |
| Verified-postmortem lifecycle + separate publisher identity | Security / grounding | Memory-admission policy (anti-poisoning) |
| Async job API (202 + poll) over a durable interrupt | Architecture | Long-running workflow lifecycle |
| Guardrails (incl. untrusted-retrieval handling) | Security | Safety layers |
| Deterministic-baseline-then-beat-it eval discipline | Testing | Eval rigor |
| Observability + cost + drift | Observability | Cost monitoring, failure modes |
| Reliability (breakers, degradation, reasoned escalation) | Error handling | Reliability engineering |
| A2A boundary | Architecture | Protocol literacy + when-not-to |
| Azure deployment (Foundry, IaC, CI/CD with test gate) | Deployment | Production cloud deployment |
