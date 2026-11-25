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


class SlackDays(list):
    """The days one read returned. `complete` is False when a day file could not be read or was too large to read: a day that is missing from the list may still be there,
    so the reader must not treat it as deleted."""

    def __init__(self, items=(), complete: bool = True):
        super().__init__(items)
        self.complete = complete


def _read_members(read, names) -> dict[str, str]:
    if "users.json" not in names:
        return {}
    try:
        return {u["id"]: u.get("real_name") or u.get("name") or u["id"] for u in json.loads(read("users.json"))}
    except (ValueError, KeyError, TypeError):
        return {}


def _day_text(raw: str, users: dict[str, str]) -> str | None:
    """The day as "Name: message" lines, an empty string for a day with nothing to read, and None when the file is not a list of messages (damaged)."""
    try:
        msgs = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(msgs, list):
        return None
    lines = []
    for m in msgs:
        if not isinstance(m, dict) or m.get("subtype") in {"channel_join", "channel_leave"} or not str(m.get("text", "")).strip():
            continue
        who = users.get(m.get("user", ""), m.get("user_name") or "Someone")
        lines.append(f"{who}: {' '.join(str(m['text']).split())}")
    return "\n".join(lines)


def _is_day_file(n: str) -> bool:
    parts = n.split("/")
    return len(parts) == 2 and parts[1].endswith(".json") and len(parts[1]) == 15 and parts[0] not in {"", "."} and ".." not in n


def _collect(read, names, skipped: bool = False) -> SlackDays:
    """`skipped` says a day file was left out before this point (too large). A day file that cannot be read, or is not a list of messages, makes the read incomplete too."""
    users = _read_members(read, names)
    out = SlackDays()
    complete = not skipped
    for n in sorted(names):
        if _is_day_file(n):
            try:
                text = _day_text(read(n), users)
            except (OSError, KeyError, zipfile.BadZipFile):
                text = None
            if text is None:
                complete = False
            elif text:
                channel, filename = n.split("/")
                out.append(SlackDay(channel, filename[:-5], text))
    out.complete = complete
    return out


def read_export(path: Path) -> SlackDays:
    path = Path(path)
    if path.is_dir():
        root = path.resolve()
        files = [p for p in root.rglob("*.json") if p.is_file() and root in p.resolve().parents]
        names = [str(p.relative_to(root)) for p in files if p.stat().st_size <= MAX_MEMBER_BYTES]
        left_out = any(p.stat().st_size > MAX_MEMBER_BYTES and _is_day_file(str(p.relative_to(root))) for p in files)
        return _collect(lambda n: (root / n).read_text(errors="replace"), names, left_out)
    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        if len(infos) > MAX_ENTRIES or sum(i.file_size for i in infos) > MAX_TOTAL_BYTES:
            raise ValueError("The Slack export is too large to read safely.")
        names = [i.filename for i in infos if not i.filename.startswith(("/", "..")) and i.file_size <= MAX_MEMBER_BYTES]
        left_out = any(i.file_size > MAX_MEMBER_BYTES and _is_day_file(i.filename) for i in infos)
        return _collect(lambda n: z.read(n).decode(errors="replace"), names, left_out)


def day_date(day: str) -> datetime:
    return datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC)
