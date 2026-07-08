"""MCP boundary — placeholder until Phase 8 (promotion, not premature complexity).

Per the architecture, the *external-system* tools are promoted to MCP servers here: a `telemetry`
server (`query_logs`, `get_metrics`) and a `platform` server (`get_deployments`,
`get_service_dependencies`). The incident/alert lookups and the RAG tools stay in-process. Each
server will front `opspilot.tools.service.ToolService` unchanged — this phase swaps the transport,
not the tool contracts. Intentionally empty until then.
"""
