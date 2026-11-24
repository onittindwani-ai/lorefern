"""Spot text that tries to give orders to the system. Ingested text is data, never instructions.

Used in three places: the answer writer never copies such a sentence, the meeting reader never turns one into a task or a decision, and the index marks the document
so a person can review it. The check is a list of patterns, not a language model, and it will miss new wording. Safety does not rest on it alone: nothing in this
system acts on text without an approval, and an owner can only be a person from the owners table.
"""

from __future__ import annotations

import re

PATTERNS = [
    r"\bignore (all |any |the |your |previous |prior |above )*(instructions?|rules?|guidelines?|polic(?:y|ies))\b",
    r"\bdisregard (all |any |the |your |previous |prior |above )*(instructions?|rules?|guidelines?)\b",
    r"\bassign (all|every|each|any)\b.{0,30}\b(tasks?|items?|work)\b",
    r"\b(mark|set|close) (all|every|each)\b.{0,30}\b(tasks?|items?|done|complete)\b",
    r"\bdelete (all|every|the)\b.{0,30}\b(tasks?|decisions?|documents?|records?|logs?)\b",
    r"\b(system|assistant|ai) (prompt|instruction|message)\b",
    r"\byou (must|should|are to|will) (now |always )?(ignore|reveal|disclose|forget|answer|assign|approve|share|send)\b",
    r"\b(reveal|disclose|print|show|share) (the |all |your )*(salary|salaries|password|passwords|secrets?|credentials?|api keys?|system prompt)\b",
    r"\bapprove (all|every|everything)\b",
    r"\bnew instructions?\b",
    r"\bact as\b",
    r"\bdo not (tell|mention|show|log|record)\b.{0,40}\b(anyone|the owner|audit|log)\b",
]
_RE = [re.compile(p, re.I) for p in PATTERNS]


def is_injection(text: str) -> bool:
    return any(r.search(text or "") for r in _RE)


def flag_lines(lines: list[str]) -> list[str]:
    return [ln for ln in lines if is_injection(ln)]


def strip_injection(sentences: list[str]) -> tuple[list[str], int]:
    kept = [s for s in sentences if not is_injection(s)]
    return kept, len(sentences) - len(kept)
