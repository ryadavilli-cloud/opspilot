"""Diagnostic-cycle contracts + one deterministic cycle.

The durable state objects the reasoning loop uses (frozen before any LLM goes inside them) and a
deterministic implementation of a single cycle: incident context -> choose next diagnostic
question -> select an approved tool -> execute -> append observation -> update hypothesis. These
contracts survive the deterministic baseline, LLM integration, MCP transport, and Azure deploy.
"""
