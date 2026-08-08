# ADR — MCP trust boundary: a security & operational contract, not just a transport (G-53)

**Status:** accepted — contract proposed/unbuilt · **Stage:** 7 · **Relates:**
[G-53](./status.md#g-53), [G-24](./status.md#g-24) · **Companion to** `deployment.md` §6 (MCP boundary)
and `decisions.md` §13.1.

Records the *MCP-trust-boundaries* decision that code-guidelines §19 requires an ADR for. The full
contract table lives in `deployment.md` §6; this ADR is the *decision that the client allowlist is not
the control*, and *where enforcement actually lives*.

---

## Context

The built parity suite proves the tool **envelope survives the network** — the *shape* is identical
in-process and over MCP. It says nothing about the properties a production network boundary must carry.
And the read-only guarantee currently rests on the client-side `READ_ONLY_TOOLS` list, which stops
*this loop* from *selecting* a write tool but does nothing to stop the identity behind a server from
*performing* a write it was granted.

## Decision

Each production MCP server carries a **security and operational contract** — the full per-concern
requirement table (protocol pinning, MI auth, per-tool authz, network isolation, timeout/retry,
rate limits, schema negotiation, trace propagation, tenant scope) lives in
[`deployment.md` §6](./deployment.md) and is not restated here. The two decisions this ADR records:

**Read-only is enforced at the server and at the identity's RBAC, not in the client.** Each server's
managed identity holds **only the underlying read permissions its own tools need** — the telemetry
server reads logs/metrics and nothing else; the platform server reads deploys/deps and nothing else. A
compromised or buggy client cannot obtain a write it was never granted.

**Incident-source tools sit behind an ITSM-owned boundary.** `get_incident` /
`get_correlated_alerts` originate from monitoring/ITSM (§2), so in production they belong behind an
incident-source adapter (an ITSM-owned boundary or its own MCP server), the same seam pattern as
telemetry/platform. In-process is the dev substitution over synthetic data.

## Consequences

- The two enforcement layers compose (client allowlist + least-privilege server identity); only the
  second survives a client bug — so the allowlist is a convenience, the RBAC is the control.
- Ownership aligns with the split: a **telemetry server** and a **platform server**; retrieval stays
  in-process (OpsPilot-owned, no ownership benefit from a network hop).
- A subagent/tool trace crossing the boundary still appears under the parent `trace_id`, keeping the
  regulated-ops audit trail intact.
