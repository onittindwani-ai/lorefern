"""Read a Slack export (a folder or a zip). Each channel and day becomes one document, and the channel decides the visibility tag.

Slack export layout (from Slack's help centre, read from memory, UNVERIFIED live): users.json, channels.json, and one folder per channel holding one JSON file per day
named YYYY-MM-DD.json, each a list of messages with `user`, `text`, `ts`, optional `thread_ts`, `subtype`. Zip entries are validated so a crafted archive cannot write
outside memory or expand without limit.
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

MAX_ENTRIES, MAX_MEMBER_BYTES, MAX_TOTAL_BYTES = 5000, 5_000_000, 100_000_000


@dataclass
class SlackDay:
    channel: str
    day: str
    text: str  # "Name: message" per line


def _read_members(read, names) -> dict[str, str]:
    if "users.json" not in names:
        return {}
    try:
        return {u["id"]: u.get("real_name") or u.get("name") or u["id"] for u in json.loads(read("users.json"))}
    except (ValueError, KeyError, TypeError):
        return {}


def _day_text(raw: str, users: dict[str, str]) -> str:
    try:
        msgs = json.loads(raw)
    except ValueError:
        return ""
    lines = []
    for m in msgs if isinstance(msgs, list) else []:
        if not isinstance(m, dict) or m.get("subtype") in {"channel_join", "channel_leave"} or not str(m.get("text", "")).strip():
            continue
        who = users.get(m.get("user", ""), m.get("user_name") or "Someone")
        lines.append(f"{who}: {' '.join(str(m['text']).split())}")
    return "\n".join(lines)


def _collect(read, names) -> list[SlackDay]:
    users = _read_members(read, names)
    out = []
    for n in sorted(names):
        parts = n.split("/")
        if len(parts) == 2 and parts[1].endswith(".json") and len(parts[1]) == 15 and parts[0] not in {"", "."} and ".." not in n:
            text = _day_text(read(n), users)
            if text:
                out.append(SlackDay(parts[0], parts[1][:-5], text))
    return out


def read_export(path: Path) -> list[SlackDay]:
    path = Path(path)
    if path.is_dir():
        root = path.resolve()
        names = [str(p.relative_to(root)) for p in root.rglob("*.json") if p.is_file() and p.stat().st_size <= MAX_MEMBER_BYTES and root in p.resolve().parents]
        return _collect(lambda n: (root / n).read_text(errors="replace"), names)
    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        if len(infos) > MAX_ENTRIES or sum(i.file_size for i in infos) > MAX_TOTAL_BYTES:
            raise ValueError("The Slack export is too large to read safely.")
        names = [i.filename for i in infos if not i.filename.startswith(("/", "..")) and i.file_size <= MAX_MEMBER_BYTES]
        return _collect(lambda n: z.read(n).decode(errors="replace"), names)


def day_date(day: str) -> datetime:
    return datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC)
