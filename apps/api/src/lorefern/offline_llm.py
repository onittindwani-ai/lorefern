"""The offline stand in for the model behind `build_llm`. It is plain rules, NOT a language model.

It answers the jobs Lorefern gives a model (see `model_tasks.py`). Each request starts with a line `[task:<name>]`; the question, the passages, the transcript and the examples
sit in marked data blocks (`source=question`, `source=passages`, `source=transcript`, ...) and the answer is JSON that matches the same schemas a real model must match:

    write_answer     {"sentences": [{"text", "passage_ids"}], "confidence", "cannot_answer"}   the extractive `RulesWriter` copies the best source sentences
    extract_meeting  {"actions": [...], "decisions": [...]}   the rules reader (`actions.py`), with the date words as spoken and the owner as named
    name_process     {"label": <the counted label>, "summary": ""}   the stand in adds no wording of its own
    review_intro     the plain sentence made from the numbers

A real model (`LLM_BACKEND=anthropic`) uses the same shapes, so the checks around it (every sentence must be supported by the cited text, every quote must be in the transcript,
a person approves every task and every send) do not change. Nothing here calls a network.
"""

from __future__ import annotations

import json
import re
from datetime import date
from types import SimpleNamespace

from lorefern import model_tasks
from lorefern.actions import extract_actions, extract_decisions
from lorefern.qa import RulesWriter
from sendora_core.llm import LLMResponse
from sendora_core.safety import UNTRUSTED_CLOSE, UNTRUSTED_OPEN


def blocks(prompt: str) -> dict[str, str]:
    """The data blocks of a prompt, by source name."""
    pat = re.escape(UNTRUSTED_OPEN) + r" source=([^\n]*)\n(.*?)\n" + re.escape(UNTRUSTED_CLOSE)
    return {m.group(1): m.group(2) for m in re.finditer(pat, prompt, re.S)}


def task_of(prompt: str) -> str:
    m = re.match(r"\[task:(\w+)\]", prompt)
    return m.group(1) if m else ""


def _json(text: str, default):
    try:
        return json.loads(text)
    except ValueError:
        return default


def _meeting(prompt: str, transcript: str) -> dict:
    d = re.search(r"MEETING_DATE: (\d{4}-\d{2}-\d{2})", prompt)
    held = date.fromisoformat(d.group(1)) if d else date.today()
    p = re.search(r"PEOPLE: (\[.*\])", prompt)
    owners = [SimpleNamespace(name=n, aliases=[n.split()[0]]) for n in _json(p.group(1), [])] if p else []
    acts, _ = extract_actions(transcript, held, owners)
    decs = extract_decisions(transcript, owners)
    return {
        "actions": [{"quote": a.quote, "title": a.title, "owner": a.owner_name or None, "due_phrase": a.due_raw or None, "confidence": int(a.confidence * 100)} for a in acts],
        "decisions": [{"quote": d.quote, "title": d.title, "decided_by": d.decided_by or None, "why": d.why, "confidence": 70} for d in decs],
    }


class OfflineBackend:
    """Same call shape as the real backends, so the whole product runs with no key and no network."""

    is_live = False
    supports_json_schema = False

    def complete(self, *, model: str, system: str, prompt: str, max_tokens: int) -> LLMResponse:
        task, data = task_of(prompt), blocks(prompt)
        if task == "review_intro":
            m = re.search(r"FACTS:\n(\{.*\})\nEND", prompt, re.S)
            return LLMResponse(model_tasks.intro_text(_json(m.group(1), {}) if m else {}), len(prompt) // 4, 60, "offline-rules")
        if task == "write_answer":
            passages = [(int(a), str(b)) for a, b in _json(data.get("passages", "[]"), [])]
            m = re.search(r"KEY_WORDS: (\[.*\])", prompt)
            terms = [(str(a), float(b)) for a, b in _json(m.group(1), [])] if m else []
            picked = RulesWriter().write(data.get("question", ""), passages, terms)
            out = {"sentences": [{"text": t, "passage_ids": [cid]} for t, cid in picked], "confidence": 70 if picked else 0, "cannot_answer": not picked}
        elif task == "extract_meeting":
            out = _meeting(prompt, data.get("transcript", ""))
        elif task == "name_process":
            m = re.search(r"LABEL: ([^\n]*)", prompt)
            out = {"label": (m.group(1) if m else "")[:60], "summary": ""}
        else:
            out = {}
        text = json.dumps(out)
        return LLMResponse(text=text, input_tokens=len(prompt) // 4, output_tokens=len(text) // 4, model="offline-rules")
