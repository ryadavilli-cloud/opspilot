"""Prompt registry + versioning: no ML stack."""

from __future__ import annotations

from pathlib import Path

import pytest

from opspilot.llm.prompts import Prompt, get_prompt


def test_registry_loads_a_seeded_prompt():
    prompt = get_prompt("evidence_selection")  # highest version
    assert isinstance(prompt, Prompt)
    assert prompt.name == "evidence_selection"
    assert "Evidence Investigator" in prompt.text
    # Pinning an explicit version is exercised against a synthetic registry below, so nothing here
    # names a version of a real prompt: a superseded prompt is deleted, and this would go with it.


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
