"""Record a single_agent scorecard from a live model into a cassette (Stage 4b).

Runs the single_agent evaluation against a live LLM (default: gpt-4o-mini via the `openai`
provider), capturing every model call to a committed cassette so CI can replay the scorecard for
free (no API). Writes the single_agent scorecard baseline alongside.

Run (records — spends on the API key):
  OPSPILOT_LLM_PROVIDER=openai OPSPILOT_LLM_MODEL=gpt-4o-mini OPSPILOT_RETRIEVAL_BACKEND=bm25 \
      python eval/record_single_agent.py
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from opspilot.llm.cassette import RecordingChatModel
from opspilot.llm.client import build_chat_model

REPO_ROOT = Path(__file__).resolve().parents[1]
CASSETTE = REPO_ROOT / "eval" / "cassettes" / "single_agent.json"
BASELINE = REPO_ROOT / "eval" / "baselines" / "single_agent_baseline.json"


def _load_scenario_eval():
    spec = importlib.util.spec_from_file_location(
        "scenario_eval", REPO_ROOT / "eval/scenario_eval.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    scenario_eval = _load_scenario_eval()
    CASSETTE.parent.mkdir(parents=True, exist_ok=True)

    recorder = RecordingChatModel(build_chat_model(), CASSETTE)  # config-resolved live model
    scorecard = scenario_eval.evaluate("single_agent", model=recorder)

    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(json.dumps(scorecard, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(scorecard, indent=2))
    print(f"\nwrote {BASELINE.relative_to(REPO_ROOT)}")
    print(f"wrote {CASSETTE.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
