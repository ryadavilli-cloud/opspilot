"""Phase 0 scaffold checks — the graph compiles and the eval harness runs empty."""

import sys
from pathlib import Path

# Make the top-level eval/ directory importable (it's a sibling of src/, not a package).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.harness import run_evals  # noqa: E402

from opspilot.config import Severity, Tier, resolve_tier  # noqa: E402
from opspilot.graph import build_graph  # noqa: E402


def test_graph_compiles() -> None:
    assert build_graph() is not None


def test_eval_harness_runs_empty() -> None:
    summary = run_evals()
    assert summary["n"] == 0


def test_severity_routing_default_ceiling_is_standard() -> None:
    # Opus is flag-gated off by default: SEV1 resolves to STANDARD (Sonnet), not PREMIUM.
    assert resolve_tier(Severity.SEV1) is Tier.STANDARD
    assert resolve_tier(Severity.SEV3) is Tier.CHEAP
