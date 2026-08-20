"""One capability, additionally served over MCP.

`get_deployments` and nothing else. The point is the protocol boundary rather than the tool: a
second way to reach one implementation, where only the transport differs and that difference is
visible. So this module dispatches to the same registered capability the investigation calls and
returns what the registry returned, unreshaped. There is no MCP-specific request model, no result
normalization, and no second evidence type; a reshaping here would make parity a property of this
code rather than of the arrangement.

Read-only follows structurally rather than by a check written here. The server exposes exactly one
tool, that tool is one of the nine read-only capabilities the registry holds, and a request naming
anything else is not a request this server can route: the protocol itself answers that the tool is
unknown. Nothing needs to inspect a call for write-shaped intent, because no write-shaped call has
anywhere to arrive.

Stdio, in process, started by whoever wants to speak to it. Nothing in the application starts this,
readiness does not probe it, and no HTTP route fronts it: the designed transport is stdio, and an
endpoint would be a different boundary wearing its name.
"""

from __future__ import annotations

from typing import Any

from opspilot.obs.tracing import span
from opspilot.tools.service import ToolService

# The transport this path records, against the `direct` the investigation records for the same
# capability. One capability, two ways in, and the activity is what tells them apart.
MCP_TRANSPORT = "mcp"

# The one tool exposed. Named here so that what the server offers is a fact about this module
# rather than a consequence of which decorators happen to have run.
EXPOSED_CAPABILITY = "get_deployments"


def build_server(service: ToolService | None = None) -> Any:
    """The stdio server, with its one tool bound to the registry.

    The service is a parameter so a test drives the same server the application ships rather than a
    stand-in of its own; left unset it builds the ordinary one over the deployed container.
    """
    from mcp.server.fastmcp import FastMCP

    # Held rather than built: starting the server and describing what it offers are answerable
    # without a backing store, and reaching for one to do that would make the exposure unusable
    # anywhere the store is not. The registry is built on the first call that needs it.
    held: list[ToolService] = [] if service is None else [service]

    def registry() -> ToolService:
        if not held:
            held.append(ToolService())
        return held[0]

    server = FastMCP(
        name="opspilot",
        instructions=(
            "Read-only access to one OpsPilot capability: deployments and configuration changes "
            "for named services in a time window."
        ),
    )

    @server.tool(name=EXPOSED_CAPABILITY)
    def get_deployments(services: list[str], start_time: str, end_time: str) -> dict[str, Any]:
        """Deployments and configuration changes for the named services in the window.

        Args:
            services: the services whose changes to read.
            start_time: ISO-8601 start of the window.
            end_time: ISO-8601 end of the window.
        """
        # The span carries the transport because that is the whole of what differs. It surrounds
        # the call it reports on, so its duration and status are the call's own.
        with span(f"tool.{EXPOSED_CAPABILITY}", attributes={"transport": MCP_TRANSPORT}) as sp:
            result = registry().call(
                EXPOSED_CAPABILITY,
                None,
                services=services,
                start_time=start_time,
                end_time=end_time,
            )
            sp.attributes["execution_outcome"] = result.outcome.value
            sp.attributes["completeness"] = result.completeness.value
            # Returned as the registry produced it. A caller of either path is looking at the same
            # envelope, which is what makes comparing them mean anything.
            return dict(result.model_dump(mode="json"))

    return server


def main() -> None:
    """Serve over stdio. This is the entry point an MCP client spawns."""
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
