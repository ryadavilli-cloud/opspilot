"""Shared retrieval primitives: the tokenizer the in-process lexical scorer runs on."""

from __future__ import annotations

import re

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())
