# OpsPilot — Technology Coverage (in / substituted / out)

**Showcase companion to [`architecture.md`](./architecture.md).** This is a coverage checklist — every
technique considered and where it landed — not part of the core architecture. It exists to make the
breadth of the survey legible; the architecture doc references it but does not depend on it.

Every technique considered, placed.

| Area | In | Substituted | Out (reason) |
|---|---|---|---|
| Frameworks | LangGraph/LangChain, ReAct, orchestrator-worker, routing, subagent-as-tool, HITL interrupts, subgraphs | — | AutoGen, CrewAI, LlamaIndex, JADE, Semantic Kernel, ADK, supervisor-with-handoffs |
| RAG / retrieval | embeddings, section chunking, multi-index, intent routing, agentic/hybrid RAG, hybrid search (dense + BM25 + RRF), cross-encoder reranker, HNSW, inverted index | `bge-small-en-v1.5` + BM25 (dev); BGE-M3 config swap; AI Search hybrid (prod); Qdrant for FAISS/Chroma | LlamaIndex advanced indexing (AI Search covers it) |
| Vector stores | in-memory index (dev) behind a `VectorIndex` protocol → Qdrant / Azure AI Search (prod) | FAISS/Chroma → Qdrant | — |
| Eval / observability | slice scorecard + versioned baseline, held-out wild generalization slice, MRR, groundedness, LLM-as-Judge, golden+synthetic sets, CI/CD gates, regression tests, LangSmith, OpenTelemetry→App Insights, DeepEval/G-Eval, drift monitoring, task-vs-system eval | — | TruLens, MLflow/W&B registry (no training) |
| Safety | read-only tool registry, citation/unsupported-claim gate, regex/injection guards, Moderation, Presidio PII, schema validation, injection classifier, fail-open/closed policy, action allowlist (v2) | — | — |
| Reliability / cost | circuit breakers, retries/backoff, timeouts, fallback chain, graceful degradation, SLAs, failure-mode framing, memory layers, tiktoken, CostTracker, budget caps, caching, prompt versioning, light model routing | Git+LangSmith for Langfuse/PromptLayer | shadow/blue-green deploy, batch API (overkill / optional) |
| Protocols | MCP (parity-proven; production split planned), A2A (boundary Agent Card only) | — | ADK (framework), ACP (co-located) |
| Fine-tuning | synthetic-data pipeline (repurposed for runbooks); Qwen as un-tuned base | — | QLoRA/LoRA/PEFT/SFTTrainer/adapter toggle (deferred, documented), vLLM/TGI, SageMaker/Bedrock |
| Multimodal / voice | subgraphs | — | Whisper/TTS/voice (possible v2 intake adapter) |
| Azure | Container Apps, Azure OpenAI, AI Search, Cosmos, Blob, Key Vault, Entra, App Insights, Event Grid, Bicep, GitHub Actions | — | — |

Clean exclusions — fine-tuning and voice — are deferred with documented rationale.
