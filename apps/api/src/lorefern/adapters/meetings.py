"""Meeting note sources. Fireflies and Fathom are read through their APIs (tier B, tested against mocks). Otter and Meetily are read from exported files.

What each provider documents (read 2026-11-23, see docs/facts/meetings.md):
  Fireflies  GraphQL at https://api.fireflies.ai/graphql, header Authorization: Bearer <key>. Transcript has date, title, sentences {speaker_name, text, start_time}, summary {action_items}.
  Fathom     REST at https://api.fathom.ai/external/v1, header X-Api-Key. GET /meetings?include_transcript=true&include_action_items=true gives items with created_at,
             title, transcript [{speaker {display_name}, text, timestamp HH:MM:SS}], action_items [{description, assignee {name}}].
  Otter      The help article could not be read (HTTP 403). The text export is assumed to be "Speaker  m:ss" then the words. UNVERIFIED.
  Meetily    The public README names no export file format for the free edition. A markdown or plain text transcript with "Speaker: words" lines is read. UNVERIFIED.
"""

from __future__ import annotations

import re

import httpx

from lorefern.adapters.base import RemoteMeeting, safe_base_url
from sendora_core.adapters import AdapterError

_LINE = re.compile(r"^\s*(?:\[[\d:]+\]\s*)?([A-Z][\w .'\-]{0,40}?)\s*:\s+(.+)$")
_OTTER_HEAD = re.compile(r"^\s*([A-Z][\w .'\-]{0,40}?)\s{2,}(\d{1,2}:\d{2}(?::\d{2})?)\s*$")


def parse_speaker_lines(text: str) -> list[tuple[str, str]]:
    """'Name: words' per line, a blank line or a new speaker starts a new turn. Lines that do not match join the turn above."""
    out: list[tuple[str, str]] = []
    for raw in text.splitlines():
        m = _LINE.match(raw)
        if m:
            out.append((m.group(1).strip(), m.group(2).strip()))
        elif raw.strip() and out and not raw.lstrip().startswith(("#", "---")):
            out[-1] = (out[-1][0], out[-1][1] + " " + raw.strip())
    return out


def parse_otter_text(text: str) -> list[tuple[str, str]]:
    """Otter style: a header line 'Speaker  0:05' then the words on the following lines."""
    out: list[tuple[str, str]] = []
    cur: str | None = None
    buf: list[str] = []
    for raw in text.splitlines():
        m = _OTTER_HEAD.match(raw)
        if m:
            if cur and buf:
                out.append((cur, " ".join(buf)))
            cur, buf = m.group(1).strip(), []
        elif raw.strip() and cur:
            buf.append(raw.strip())
    if cur and buf:
        out.append((cur, " ".join(buf)))
    return out


def meeting_from_file(name: str, raw: str, provider: str, held_on: str, title: str = "") -> RemoteMeeting:
    lines = parse_otter_text(raw) if provider == "otter" else parse_speaker_lines(raw)
    return RemoteMeeting(name, title or name.rsplit(".", 1)[0].replace("-", " ").title(), held_on, provider, lines)


class FirefliesMeetings:
    def __init__(self, settings, client: httpx.Client | None = None):
        self.settings = settings
        if not settings.fireflies_token:
            raise AdapterError("FIREFLIES_TOKEN is empty.")
        self.client = client or httpx.Client(base_url=safe_base_url(settings.fireflies_base_url), timeout=30)

    QUERY = "query { transcripts(limit: 50) { id title date sentences { speaker_name text } summary { action_items } participants } }"

    def list_meetings(self) -> list[RemoteMeeting]:
        r = self.client.post("/graphql", headers={"Authorization": f"Bearer {self.settings.fireflies_token}"}, json={"query": self.QUERY})
        if r.status_code in (401, 403):
            raise AdapterError("Fireflies refused the key. Copy a new API key from the Integrations page of your Fireflies account.")
        r.raise_for_status()
        out = []
        for t in (r.json().get("data") or {}).get("transcripts") or []:
            date = str(t.get("date") or "")[:10]
            if date.isdigit():  # milliseconds since 1970
                from datetime import UTC, datetime

                date = datetime.fromtimestamp(int(t["date"]) / 1000, UTC).strftime("%Y-%m-%d")
            lines = [(s.get("speaker_name") or "Unknown", s.get("text") or "") for s in t.get("sentences") or [] if (s.get("text") or "").strip()]
            ai = (t.get("summary") or {}).get("action_items") or ""
            out.append(RemoteMeeting(str(t["id"]), t.get("title") or "Meeting", date, "fireflies", lines, list(t.get("participants") or []), [x.strip("* -") for x in ai.splitlines() if x.strip()] if isinstance(ai, str) else []))
        return out

    def healthcheck(self):
        try:
            self.list_meetings()
            return True, "Connected."
        except Exception as exc:
            return False, str(exc) if isinstance(exc, AdapterError) else f"Could not reach Fireflies: {type(exc).__name__}."


class FathomMeetings:
    def __init__(self, settings, client: httpx.Client | None = None):
        self.settings = settings
        if not settings.fathom_token:
            raise AdapterError("FATHOM_TOKEN is empty.")
        self.client = client or httpx.Client(base_url=safe_base_url(settings.fathom_base_url), timeout=30)

    def list_meetings(self) -> list[RemoteMeeting]:
        out, cursor = [], None
        for _ in range(20):
            params = {"include_transcript": "true", "include_action_items": "true", **({"cursor": cursor} if cursor else {})}
            r = self.client.get("/external/v1/meetings", params=params, headers={"X-Api-Key": self.settings.fathom_token})
            if r.status_code in (401, 403):
                raise AdapterError("Fathom refused the key. Create a new API key in your Fathom settings.")
            r.raise_for_status()
            body = r.json()
            for m in body.get("items", []):
                lines = [((t.get("speaker") or {}).get("display_name") or "Unknown", t.get("text") or "") for t in m.get("transcript") or [] if (t.get("text") or "").strip()]
                items = [a.get("description", "") for a in m.get("action_items") or []]
                out.append(RemoteMeeting(str(m.get("recording_id")), m.get("title") or m.get("meeting_title") or "Meeting", str(m.get("created_at", ""))[:10], "fathom", lines, [], items))
            cursor = body.get("next_cursor")
            if not cursor:
                break
        return out

    def healthcheck(self):
        try:
            self.list_meetings()
            return True, "Connected."
        except Exception as exc:
            return False, str(exc) if isinstance(exc, AdapterError) else f"Could not reach Fathom: {type(exc).__name__}."


def load_transcript_file(path) -> RemoteMeeting:
    """A transcript file with a small header (title, date, provider, visibility) then `---` then the transcript in the provider's text layout."""
    from pathlib import Path

    p = Path(path)
    raw = p.read_text(encoding="utf-8", errors="replace")
    head, _, body = raw.partition("\n---\n")
    meta = {k.strip().lower(): v.strip() for k, v in (ln.split(":", 1) for ln in head.splitlines() if ":" in ln)}
    provider = meta.get("provider", "file")
    m = meeting_from_file(p.name, body, provider, meta.get("date", ""), meta.get("title", ""))
    m.external_id = p.stem
    return m


def visibility_of(path) -> str:
    from pathlib import Path

    head = Path(path).read_text(encoding="utf-8", errors="replace").partition("\n---\n")[0]
    for ln in head.splitlines():
        if ln.lower().startswith("visibility:"):
            return ln.split(":", 1)[1].strip()
    return ""


class FileMeetings:
    """Transcript text files in `<KNOWLEDGE_DIR>/meetings`. Each file may start with a small header (title, date, provider, visibility)."""

    MAX_BYTES = 5_000_000

    def __init__(self, settings):
        self.settings = settings

    def _dir(self):
        from pathlib import Path

        return Path(self.settings.knowledge_dir) / "meetings" if self.settings.knowledge_dir else None

    def list_meetings(self) -> list[RemoteMeeting]:
        d, out = self._dir(), []
        if d is None or not d.is_dir():
            return out
        root = d.resolve()
        for p in sorted(d.glob("*.txt")):
            if p.is_symlink() or root not in p.resolve().parents or p.stat().st_size > self.MAX_BYTES:
                continue
            m = load_transcript_file(p)
            m.visibility = visibility_of(p)  # type: ignore[attr-defined]
            out.append(m)
        return out

    def healthcheck(self):
        d = self._dir()
        if d is None:
            return False, "KNOWLEDGE_DIR is empty."
        return (True, f"{len(self.list_meetings())} transcript files found.") if d.is_dir() else (False, "There is no meetings folder inside KNOWLEDGE_DIR.")
