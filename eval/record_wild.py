"""Record the RCAEval wild-slice generalization scorecard (Stage 4d).

Runs deterministic + single_agent on the held-out Online Boutique slice and writes
`eval/baselines/wild_scorecard.json`, recording the single_agent cassette so the probe is
reproducible locally (it needs the gitignored RE1-OB data, so this is a LOCAL probe, not a CI gate).

Run:
  OPSPILOT_LLM_PROVIDER=openai OPSPILOT_LLM_MODEL=gpt-4o-mini python eval/record_wild.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from opspilot.llm.cassette import RecordingChatModel
from opspilot.llm.client import build_chat_model

REPO_ROOT = Path(__file__).resolve().parents[1]
CASSETTE = REPO_ROOT / "eval" / "cassettes" / "wild_single_agent.json"
SCORECARD = REPO_ROOT / "eval" / "baselines" / "wild_scorecard.json"


def _load_wild():
    spec = importlib.util.spec_from_file_location("wild", REPO_ROOT / "eval/wild.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # @dataclass in the module needs it registered in sys.modules
    spec.loader.exec_module(module)
    return module


def main() -> None:
    wild = _load_wild()
    det = wild.evaluate_wild("deterministic")
    if not det["n_cases"]:
        print(det.get("note", "no cases"))
        return

    CASSETTE.parent.mkdir(parents=True, exist_ok=True)
    recorder = RecordingChatModel(build_chat_model(), CASSETTE)
    sa = wild.evaluate_wild("single_agent", model=recorder)

    out = {
        "probe": "RCAEval RE1 Online Boutique (held-out); metrics-only; root-service RCA",
        "n_cases": sa["n_cases"],
        "deterministic_rca": det["rca_correctness"],
        "single_agent_rca": sa["rca_correctness"],
        "single_agent_per_case": sa["per_case"],
    }
    SCORECARD.parent.mkdir(parents=True, exist_ok=True)
    SCORECARD.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "single_agent_per_case"}, indent=2))
    print(f"wrote {SCORECARD.name} and {CASSETTE.name}")


if __name__ == "__main__":
    main()
