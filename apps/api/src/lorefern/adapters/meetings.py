"""Meeting note sources. Fireflies and Fathom are read through their APIs (tier B, tested against mocks). Otter and Meetily are read from exported files.

What each provider documents (read 2026-11-23, see docs/facts/meetings.md):
  Fireflies  GraphQL at https://api.fireflies.ai/graphql, header Authorization: Bearer <key>. Transcript has date, title, sentences {speaker_name, text, start_time}, summary {action_items}.
  Fathom     REST at https://api.fathom.ai/external/v1, header X-Api-Key. GET /meetings?include_transcript=true&include_action_items=true gives items with created_at,
             title, transcript [{speaker {display_name}, text, timestamp HH:MM:SS}], action_items [{description, assignee {name}}].
  Otter      The help article could not be read (HTTP 403). The text export is assumed to be "Speaker  m:ss" then the words. UNVERIFIED.
  Meetily    The public README names no export file format for the free edition. A markdown or plain text transcript with "Speaker: words" lines is read. UNVERIFIED.
"""

from __future__ import annotations

import os
import re

import httpx

from lorefern.adapters.base import RemoteMeeting, RemoteMeetings, safe_base_url
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


def _json_body(r: httpx.Response, who: str):
    """The reply as JSON. A reply that is not JSON (a maintenance page) is an error, never an empty list of meetings."""
    try:
        return r.json()
    except ValueError as exc:
        raise AdapterError(f"{who} answered with something that is not JSON, so nothing was read and nothing was removed.") from exc


def _fireflies_transcripts(body) -> list[dict]:
    """The `transcripts` list of a Fireflies reply, only when the reply has the documented shape. A GraphQL `errors` entry, a null `data` or `transcripts`, or any other shape is an
    incomplete read (an error): "no meetings came back" is not the same as "there are no meetings", and only the second may remove anything."""
    if not isinstance(body, dict):
        raise AdapterError("Fireflies answered in a shape that was not expected, so nothing was read and nothing was removed.")
    if body.get("errors"):
        raise AdapterError("Fireflies answered with an error (for example a rate limit), so nothing was read and nothing was removed. It will be tried again.")
    data = body.get("data")
    found = data.get("transcripts") if isinstance(data, dict) else None
    if not isinstance(found, list) or not all(isinstance(t, dict) and "id" in t for t in found):
        raise AdapterError("Fireflies answered without the list of transcripts (a wrong or swapped key, or a change on their side), so nothing was read and nothing was removed.")
    return found


def _fathom_items(body) -> tuple[list[dict], str | None]:
    """The `items` and the next cursor of a Fathom reply, only when the reply has the documented shape (see `_fireflies_transcripts`)."""
    items = body.get("items") if isinstance(body, dict) else None
    if not isinstance(items, list) or not all(isinstance(m, dict) for m in items):
        raise AdapterError("Fathom answered without the list of meetings (a wrong key, or a change on their side), so nothing was read and nothing was removed.")
    cursor = body.get("next_cursor")
    return items, cursor if isinstance(cursor, str) and cursor else None


class FirefliesMeetings:
    def __init__(self, settings, client: httpx.Client | None = None):
        self.settings = settings
        if not settings.fireflies_token:
            raise AdapterError("FIREFLIES_TOKEN is empty.")
        self.client = client or httpx.Client(base_url=safe_base_url(settings.fireflies_base_url), timeout=30)

    LIMIT = 50
    QUERY = "query { transcripts(limit: %d) { id title date sentences { speaker_name text } summary { action_items } participants } }" % LIMIT

    def list_meetings(self) -> RemoteMeetings:
        r = self.client.post("/graphql", headers={"Authorization": f"Bearer {self.settings.fireflies_token}"}, json={"query": self.QUERY})
        if r.status_code in (401, 403):
            raise AdapterError("Fireflies refused the key. Copy a new API key from the Integrations page of your Fireflies account.")
        r.raise_for_status()
        found = _fireflies_transcripts(_json_body(r, "Fireflies"))
        out = RemoteMeetings(complete=len(found) < self.LIMIT)  # a full page may have more behind it, so it is not known to be everything
        for t in found:
            date = str(t.get("date") or "")[:10]
            if date.isdigit():  # milliseconds since 1970
                from datetime import UTC, datetime

                date = datetime.fromtimestamp(int(t["date"]) / 1000, UTC).strftime("%Y-%m-%d")
            lines = [(s.get("speaker_name") or "Unknown", s.get("text") or "") for s in t.get("sentences") or [] if isinstance(s, dict) and (s.get("text") or "").strip()]
            ai = (t.get("summary") or {}).get("action_items") or ""
            out.append(RemoteMeeting(str(t["id"]), t.get("title") or "Meeting", date, "fireflies", lines, list(t.get("participants") or []), [x.strip("* -") for x in ai.splitlines() if x.strip()] if isinstance(ai, str) else []))
        return out

    def healthcheck(self):
        """One small request (who the key belongs to), never a download of 50 transcripts."""
        try:
            r = self.client.post("/graphql", headers={"Authorization": f"Bearer {self.settings.fireflies_token}"}, json={"query": "query { user { user_id } }"})
            if r.status_code in (401, 403):
                raise AdapterError("Fireflies refused the key. Copy a new API key from the Integrations page of your Fireflies account.")
            r.raise_for_status()
            return True, "Connected."
        except Exception as exc:
            return False, str(exc) if isinstance(exc, AdapterError) else f"Could not reach Fireflies: {type(exc).__name__}."


class FathomMeetings:
    def __init__(self, settings, client: httpx.Client | None = None):
        self.settings = settings
        if not settings.fathom_token:
            raise AdapterError("FATHOM_TOKEN is empty.")
        self.client = client or httpx.Client(base_url=safe_base_url(settings.fathom_base_url), timeout=30)

    def list_meetings(self) -> RemoteMeetings:
        out, cursor = RemoteMeetings(), None
        for _ in range(20):
            params = {"include_transcript": "true", "include_action_items": "true", **({"cursor": cursor} if cursor else {})}
            r = self.client.get("/external/v1/meetings", params=params, headers={"X-Api-Key": self.settings.fathom_token})
            if r.status_code in (401, 403):
                raise AdapterError("Fathom refused the key. Create a new API key in your Fathom settings.")
            r.raise_for_status()
            items, cursor = _fathom_items(_json_body(r, "Fathom"))
            for m in items:
                lines = [((t.get("speaker") or {}).get("display_name") or "Unknown", t.get("text") or "") for t in m.get("transcript") or [] if isinstance(t, dict) and (t.get("text") or "").strip()]
                items = [a.get("description", "") for a in m.get("action_items") or []]
                out.append(RemoteMeeting(str(m.get("recording_id")), m.get("title") or m.get("meeting_title") or "Meeting", str(m.get("created_at", ""))[:10], "fathom", lines, [], items))
            if not cursor:
                out.complete = True  # paged to the end
                break
        return out

    def healthcheck(self):
        """One small request (the first page of meetings, without transcripts), never every page with every transcript."""
        try:
            r = self.client.get("/external/v1/meetings", headers={"X-Api-Key": self.settings.fathom_token})
            if r.status_code in (401, 403):
                raise AdapterError("Fathom refused the key. Create a new API key in your Fathom settings.")
            r.raise_for_status()
            return True, "Connected."
        except Exception as exc:
            return False, str(exc) if isinstance(exc, AdapterError) else f"Could not reach Fathom: {type(exc).__name__}."


_INVISIBLE = {ord(c): None for c in "\ufeff\u200b\u200c\u200d\u2060\u00ad\x00"}  # byte order mark, zero width characters, soft hyphen and NUL: invisible in an editor, fatal to a string match
_HEADER_END = re.compile(r"\n[ \t]*---[ \t]*(?:\n|$)")


def split_header(raw: str) -> tuple[list[str], str]:
    """The header lines of a transcript file (each stripped of invisible characters and of indentation) and the body after the `---` line. Windows line ends, a byte order mark, a
    zero width character or an indented line cannot hide a header line. A file with no `---` line is all header and has no body (as it always was), so a `visibility:` line anywhere in it
    is still honoured."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n").translate(_INVISIBLE)
    m = _HEADER_END.search("\n" + text)
    if m is None:
        return [ln.strip() for ln in text.split("\n") if ln.strip()], ""
    head, body = ("\n" + text)[: m.start()], ("\n" + text)[m.end():]
    return [ln.strip() for ln in head.split("\n") if ln.strip()], body


def header_fields(lines: list[str]) -> dict[str, str]:
    """`key: value` per header line, keys in lower case. A key may have spaces around its colon. The first line of a key wins."""
    out: dict[str, str] = {}
    for ln in lines:
        if ":" in ln:
            k, v = ln.split(":", 1)
            out.setdefault(k.strip().lower(), v.strip())
    return out


def load_transcript_file(path) -> RemoteMeeting:
    """A transcript file with a small header (title, date, provider, visibility) then `---` then the transcript in the provider's text layout."""
    from pathlib import Path

    p = Path(path)
    head, body = split_header(p.read_text(encoding="utf-8", errors="replace"))
    meta = header_fields(head)
    provider = meta.get("provider", "file")
    m = meeting_from_file(p.name, body, provider, meta.get("date", ""), meta.get("title", ""))
    m.external_id = p.stem
    return m


def visibility_of(path) -> str:
    """The tag a transcript file writes about itself in its header ("" when it writes none)."""
    from pathlib import Path

    head, _ = split_header(Path(path).read_text(encoding="utf-8", errors="replace"))
    return header_fields(head).get("visibility", "")


class FileMeetings:
    """Transcript text files in `<KNOWLEDGE_DIR>/meetings`. Each file may start with a small header (title, date, provider, visibility)."""

    MAX_BYTES = 5_000_000

    def __init__(self, settings):
        self.settings = settings

    def _dir(self):
        from pathlib import Path

        return Path(self.settings.knowledge_dir) / "meetings" if self.settings.knowledge_dir else None

    def list_meetings(self) -> RemoteMeetings:
        """Complete only when the folder is there, could be listed, and every transcript file in it was read: a file that is skipped (a link, too large, unreadable), a folder that is not
        there and a folder that cannot be listed are not deleted meetings."""
        d, out = self._dir(), RemoteMeetings()
        if d is None or not d.is_dir():
            return out
        try:
            root = d.resolve()
            with os.scandir(d) as entries:  # a folder the app may not read raises here, where `glob` would quietly return an empty list
                names = sorted(e.name for e in entries if e.name.endswith(".txt"))
        except OSError:
            return out
        complete = True
        for name in names:
            p = d / name
            try:
                if p.is_dir():
                    continue
                if p.is_symlink() or root not in p.resolve().parents or p.stat().st_size > self.MAX_BYTES:
                    complete = False
                    continue
                m = load_transcript_file(p)
                m.visibility = visibility_of(p)  # type: ignore[attr-defined]
            except OSError:
                complete = False
                continue
            out.append(m)
        out.complete = complete
        return out

    def healthcheck(self):
        d = self._dir()
        if d is None:
            return False, "KNOWLEDGE_DIR is empty."
        return (True, f"{len(self.list_meetings())} transcript files found.") if d.is_dir() else (False, "There is no meetings folder inside KNOWLEDGE_DIR.")
