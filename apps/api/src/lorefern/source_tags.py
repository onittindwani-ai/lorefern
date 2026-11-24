"""Changing a source's visibility, and changing it back.

A restricted source fixes the tag of everything in it, and everything made from it: documents, their passages, meetings, and the tasks and decisions found in those meetings.
The tag each row had before is saved in the state table, so setting the source back to `company` puts every row back exactly as it was, and no restricted row is left behind
in a more open source.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from lorefern.context import get_state, set_state
from lorefern.models import Decision, Document, Meeting, Task


def _key(source_id: int) -> str:
    return f"own_tags:{source_id}"


def _rows(s: Session, source_id: int):
    docs = list(s.scalars(select(Document).where(Document.source_id == source_id)))
    meetings = list(s.scalars(select(Meeting).where(Meeting.source_id == source_id)))
    mids = [m.id for m in meetings]
    tasks = list(s.scalars(select(Task).where(Task.meeting_id.in_(mids)))) if mids else []
    decisions = list(s.scalars(select(Decision).where(Decision.meeting_id.in_(mids)))) if mids else []
    return {"d": docs, "m": meetings, "t": tasks, "x": decisions}


def restrict(s: Session, source_id: int, tag: str) -> int:
    """Give every row of the source this tag. The first time a row is restricted its own tag is saved. Returns how many rows were changed."""
    saved: dict[str, dict[str, str]] = json.loads(get_state(s, _key(source_id), "") or "{}")
    changed = 0
    for kind, rows in _rows(s, source_id).items():
        keep = saved.setdefault(kind, {})
        for r in rows:
            keep.setdefault(str(r.id), r.tag)
            if r.tag != tag:
                r.tag, changed = tag, changed + 1
            if kind == "d":
                r.content_hash = f"retagged:{tag}"  # the next read sees a change and applies the source's tag rule again
                for c in r.chunks:
                    c.tag = tag
    set_state(s, _key(source_id), json.dumps(saved))
    s.flush()
    return changed


def restore(s: Session, source_id: int) -> int:
    """Put every saved tag back and forget the save. Returns how many rows were changed."""
    saved = json.loads(get_state(s, _key(source_id), "") or "{}")
    changed = 0
    for kind, rows in _rows(s, source_id).items():
        was = saved.get(kind, {})
        for r in rows:
            old = was.get(str(r.id))
            if old and r.tag != old:
                r.tag, changed = old, changed + 1
                if kind == "d":
                    for c in r.chunks:
                        c.tag = old
    set_state(s, _key(source_id), "")
    s.flush()
    return changed
