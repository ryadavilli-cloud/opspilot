"""FastAPI surface. /health (Phase 0) + POST /investigate (Phase 1)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from opspilot import __version__
from opspilot.graph import _initial_state, build_graph

app = FastAPI(title="OpsPilot", version=__version__)
_graph = build_graph()

# Composition root: one ToolService per process, injected into the graph via config (built
# lazily so importing this module stays free of the retrieval/ML stack). This replaces the old
# module-global singleton that lived inside the graph nodes.
_tool_service = None


def _service():
    global _tool_service
    if _tool_service is None:
        from opspilot.tools.service import ToolService

        _tool_service = ToolService()
    return _tool_service


class Alert(BaseModel):
    incident_id: str | None = None
    severity: str | None = None
    category: str | None = None
    summary: str = ""


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.post("/investigate")
def investigate(alert: Alert) -> dict[str, Any]:
    result = _graph.invoke(
        _initial_state(alert.model_dump()),
        config={"configurable": {"tool_service": _service()}},
    )
    return {
        "incident_id": result.get("incident_id"),
        "report": result.get("report"),
        "approval": result.get("approval"),
        "postmortem": result.get("postmortem"),
    }
