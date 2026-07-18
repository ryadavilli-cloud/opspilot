"""Versioned prompt registry.

Prompts live in-repo as files under ``prompts/`` named ``<name>.v<N>.md``. `get_prompt(name)`
returns the highest version (or a pinned one via ``version=``) and the version string is stamped
into `ChatResult.prompt_version` so every model call is attributable to the exact prompt text that
produced it. Versioning is append-only: to change a prompt, add a new ``.vN`` file rather than
editing an old one, so recorded evals stay reproducible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_NAME_RE = re.compile(r"^(?P<name>.+)\.v(?P<n>\d+)\.md$")


@dataclass(frozen=True)
class Prompt:
    """A resolved prompt. `version` (e.g. ``diagnose_planner.v1``) is the audit-log stamp."""

    name: str
    version: str
    text: str


def _discover(prompts_dir: Path) -> dict[str, dict[int, Path]]:
    found: dict[str, dict[int, Path]] = {}
    for path in prompts_dir.glob("*.md"):
        match = _NAME_RE.match(path.name)
        if match:
            found.setdefault(match["name"], {})[int(match["n"])] = path
    return found


def get_prompt(
    name: str,
    *,
    version: int | None = None,
    prompts_dir: Path | None = None,
) -> Prompt:
    """Load a prompt by name — highest version by default, or a pinned `version`.

    Unknown name or missing version -> KeyError (fail loud).
    """
    directory = prompts_dir or _PROMPTS_DIR
    versions = _discover(directory).get(name)
    if not versions:
        raise KeyError(f"no prompt named {name!r} in {directory}")
    number = max(versions) if version is None else version
    if number not in versions:
        raise KeyError(f"prompt {name!r} has no version v{number}; have {sorted(versions)}")
    return Prompt(
        name=name,
        version=f"{name}.v{number}",
        text=versions[number].read_text(encoding="utf-8").strip(),
    )
