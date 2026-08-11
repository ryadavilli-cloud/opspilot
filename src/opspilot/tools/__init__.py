"""Investigation tools.

Eight read-only capabilities exposed via `ToolService`: six deterministic
(incident/alert/deployment/logs/metrics/dependencies) over the repository, and two retrieval
capabilities over the hybrid Retriever.

`CAPABILITY_NAMES` is the single capability inventory. The registry is built against it and the
read-only check reads from it, so there is one list rather than two that can drift. A mutating
capability is not absent by convention; it is absent from this tuple, which is what makes the
read-only property structural.
"""

CAPABILITY_NAMES: tuple[str, ...] = (
    "get_incident",
    "get_correlated_alerts",
    "get_deployments",
    "query_logs",
    "get_metrics",
    "get_service_dependencies",
    "search_runbooks",
    "search_past_incidents",
)

# Imported after the inventory it depends on, so the module initializes in one pass.
from opspilot.tools.service import ToolService  # noqa: E402

__all__ = ["CAPABILITY_NAMES", "ToolService"]
