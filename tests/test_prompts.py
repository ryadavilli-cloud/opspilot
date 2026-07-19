"""Prompt registry + versioning (Stage 4a) — no ML stack."""

from __future__ import annotations

from pathlib import Path

import pytest

from opspilot.llm.prompts import Prompt, get_prompt


def test_registry_loads_seeded_planner_prompt():
    prompt = get_prompt("diagnose_planner")  # highest version
    assert isinstance(prompt, Prompt)
    assert prompt.name == "diagnose_planner"
    assert "on-call SRE" in prompt.text
    # versioning is append-only: v1 stays pinnable even after later versions land
    assert get_prompt("diagnose_planner", version=1).version == "diagnose_planner.v1"


def test_latest_version_selected(tmp_path: Path):
    (tmp_path / "greet.v1.md").write_text("one", encoding="utf-8")
    (tmp_path / "greet.v2.md").write_text("two", encoding="utf-8")
    assert get_prompt("greet", prompts_dir=tmp_path).version == "greet.v2"
    assert get_prompt("greet", prompts_dir=tmp_path).text == "two"
    assert get_prompt("greet", version=1, prompts_dir=tmp_path).text == "one"


def test_unknown_name_and_version(tmp_path: Path):
    (tmp_path / "greet.v1.md").write_text("one", encoding="utf-8")
    with pytest.raises(KeyError):
        get_prompt("missing", prompts_dir=tmp_path)
    with pytest.raises(KeyError):
        get_prompt("greet", version=9, prompts_dir=tmp_path)
