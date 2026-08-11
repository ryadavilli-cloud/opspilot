"""G-18 (Stage 5e): the deploy-regression path never cites a deploy that FOLLOWED onset as causal.

`get_deployments` looks up to onset+15min, so a post-onset deploy is in the results. run_cycle must
clamp to `d.ts <= onset` before naming the "preceding onset" deploy — otherwise it blames a change
that came after the symptoms. Unit-tested with a minimal ToolService stand-in, no corpus needed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from opspilot.diagnosis.contracts import (
    DiagnosisContext,
    DiagnosticQuestion,
    InvestigationPlan,
    ToolCallRequest,
)
from opspilot.diagnosis.cycle import run_cycle
from opspilot.tools.contracts import (
    Completeness,
    DeploymentRecord,
    ExecutionOutcome,
    ToolMetadata,
    ToolResult,
)
from opspilot.tools.service import ToolService

ONSET = datetime(2026, 7, 1, 9, 0, 0, tzinfo=UTC)


def _deploy(deploy_id: str, minutes_from_onset: int) -> DeploymentRecord:
    return DeploymentRecord(
        deploy_id=deploy_id,
        service="payment-api",
        ts=ONSET + timedelta(minutes=minutes_from_onset),
        version="v1.2.3",
        note="",
    )


class _DeployService(ToolService):
    """Returns canned get_deployments results; skips the real corpus load (only `call` is used)."""

    def __init__(self, deploys: list[DeploymentRecord]) -> None:  # noqa: D401 - test stub
        self._deploys = deploys

    def call(self, tool_name: str, **kwargs: Any) -> ToolResult[Any]:
        meta = ToolMetadata(tool_name=tool_name, duration_ms=1.0, result_count=len(self._deploys))
        if tool_name == "get_deployments":
            refs = [f"deploys:{d.service}:{d.deploy_id}" for d in self._deploys]
            return ToolResult(
                tool_name=tool_name,
                outcome=ExecutionOutcome.SUCCEEDED,
                completeness=Completeness.COMPLETE,
                results=self._deploys,
                evidence_refs=refs,
                metadata=meta,
            )
        return ToolResult(
            tool_name=tool_name,
            outcome=ExecutionOutcome.SUCCEEDED,
            completeness=Completeness.EMPTY,
            metadata=ToolMetadata(tool_name=tool_name, duration_ms=1.0, result_count=0),
        )


def _plan() -> InvestigationPlan:
    return InvestigationPlan(
        max_iters=5,
        questions=[
            DiagnosticQuestion(
                key="deployments",
                question="what changed?",
                call=ToolCallRequest(tool="get_deployments"),
            )
        ],
    )


def _ctx() -> DiagnosisContext:
    return DiagnosisContext(
        incident_id="inc-x", affected_services=["payment-api"], onset=ONSET.isoformat()
    )


def test_pre_onset_deploy_is_cited():
    hyp, _, _, _ = run_cycle(_DeployService([_deploy("dep-before", -10)]), _ctx(), _plan())
    assert any(c.ref == "deploys:payment-api:dep-before" for c in hyp.citations)
    assert "deployment regression" in hyp.statement.lower()


def test_post_onset_deploy_is_not_cited_as_causal():
    # A deploy 10 min AFTER onset cannot have preceded the symptoms — it must not be cited, and the
    # hypothesis must not claim a deployment regression.
    hyp, _, _, _ = run_cycle(_DeployService([_deploy("dep-after", +10)]), _ctx(), _plan())
    assert not any(c.source == "deploys" for c in hyp.citations)
    assert "deployment regression" not in hyp.statement.lower()


def test_latest_pre_onset_deploy_wins_over_post_onset():
    # Two pre-onset + one post-onset: the closest-before-onset is cited, never the later post-onset.
    svc = _DeployService(
        [_deploy("dep-old", -60), _deploy("dep-recent", -5), _deploy("dep-after", +12)]
    )
    hyp, _, _, _ = run_cycle(svc, _ctx(), _plan())
    deploy_refs = [c.ref for c in hyp.citations if c.source == "deploys"]
    assert deploy_refs == ["deploys:payment-api:dep-recent"]
