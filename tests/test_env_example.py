"""Every env var config.py reads must have a key in .env.example, checked by a small test
rather than by eye, so the two cannot silently drift apart again."""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ENV_READ = re.compile(r'\b_(?:dir_)?env(?:_int|_flag)?\(\s*"([A-Z][A-Z0-9_]*)"')
_ENV_KEY = re.compile(r"^([A-Z][A-Z0-9_]*)=", re.MULTILINE)


def test_every_config_env_var_is_documented() -> None:
    config_src = (_REPO_ROOT / "src" / "opspilot" / "config.py").read_text(encoding="utf-8")
    example = (_REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    read_vars = set(_ENV_READ.findall(config_src))
    documented = set(_ENV_KEY.findall(example))
    missing = read_vars - documented
    assert not missing, f"config.py reads env vars missing from .env.example: {sorted(missing)}"
