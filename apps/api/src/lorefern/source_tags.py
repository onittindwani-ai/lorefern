"""Changing a source's visibility, and changing it back.

A restricted source fixes the tag of everything in it, and everything made from it: documents, their passages, meetings, and the tasks and decisions found in those meetings.
A row that already has a narrower tag keeps it: a retag never lets an audience see a row it could not see before. For every row the state table keeps a pair: the tag the row
would have in an open source (`own`: what its file, folder or header says) and the tag the restriction gave it (`given`). Every read of a restricted source refreshes the
`own` side, so a file that was narrowed while the source was restricted is remembered as narrow.
Setting the source back to `company` puts back `own` on a row that still holds `given`. A row whose tag moved since (a re import or a new line in a file narrowed it) keeps the
narrower tag it has. Every document is also marked as changed, so the next read works its tag out again from the file, and a file that changed meanwhile is corrected by it.
Text that was built from the rows earlier (weekly reviews, process evidence, stored answers) is cleared when a row is narrowed, because it may quote what is now restricted.
"""

from __future__ import annotations

import json

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from lorefern import search
from lorefern.context import get_state, set_state
from lorefern.models import Decision, Document, Meeting, Process, Question, Task, WeeklyReview
from lorefern.visibility import AUDIENCES, audiences_of, meet_tag

RETAGGED = "retagged:"  # the content hash of a document whose tag was set from outside: the next read sees a change and works the tag out again


def _key(source_id: int) -> str:
    return f"own_tags:{source_id}"


def _rows(s: Session, source_id: int):
    docs = list(s.scalars(select(Document).where(Document.source_id == source_id)))
    meetings = list(s.scalars(select(Meeting).where(Meeting.source_id == source_id)))
    mids = [m.id for m in meetings]
    tasks = list(s.scalars(select(Task).where(Task.meeting_id.in_(mids)))) if mids else []
    decisions = list(s.scalars(select(Decision).where(Decision.meeting_id.in_(mids)))) if mids else []
    return {"d": docs, "m": meetings, "t": tasks, "x": decisions}


def _load(s: Session, source_id: int) -> dict[str, dict[str, list[str]]]:
    """The saved pairs, [own, given] per row id and kind. A value saved by an older version is a bare tag: its `given` is unknown (empty)."""
    raw = json.loads(get_state(s, _key(source_id), "") or "{}")
    return {kind: {rid: (list(v) if isinstance(v, list) else [str(v), ""]) for rid, v in rows.items()} for kind, rows in raw.items()}


def _save(s: Session, source_id: int, saved: dict) -> None:
    set_state(s, _key(source_id), json.dumps(saved))


def restrict(s: Session, source_id: int, tag: str) -> int:
    """Give every row of the source this tag, or a narrower one it already has. The first time a row is restricted its own tag is saved, and every time the tag it was given is.
    Returns how many rows were changed."""
    saved = _load(s, source_id)
    changed = 0
    for kind, rows in _rows(s, source_id).items():
        keep = saved.setdefault(kind, {})
        for r in rows:
            own = keep.get(str(r.id), [r.tag, ""])[0]
            new = meet_tag(r.tag, tag)
            if r.tag != new:
                r.tag, changed = new, changed + 1
            keep[str(r.id)] = [own, r.tag]
            if kind == "d":
                r.content_hash = f"{RETAGGED}{tag}"  # the next read sees a change and applies the source's tag rule again
                for c in r.chunks:
                    c.tag = r.tag
    _save(s, source_id, saved)
    if changed:
        scrub_derived(s, tag)
    search.clear_cache()
    s.flush()
    return changed


def note_own(s: Session, source_id: int, kind: str, own: dict[int, str]) -> None:
    """A read of a restricted source worked out what each row would be tagged in an open source (`own`, by row id). Save it next to the tag the row holds now, so setting the source back
    to `company` gives each row the tag its file or header really says, including a tag written after the source was restricted."""
    if not own:
        return
    saved = _load(s, source_id)
    keep = saved.setdefault(kind, {})
    model = {"d": Document, "m": Meeting, "t": Task, "x": Decision}[kind]
    ids = list(own)
    for i in range(0, len(ids), 500):
        for rid, tag in s.execute(select(model.id, model.tag).where(model.id.in_(ids[i:i + 500]))):
            keep[str(rid)] = [own[rid], tag]
    _save(s, source_id, saved)
    s.flush()


def scrub_derived(s: Session, tag: str) -> None:
    """Text built earlier from the rows may quote what is now restricted: weekly reviews and process evidence are rebuilt by the next job, and answers stored for audiences
    that can no longer see this tag are emptied (the answer list a person sees never shows them, but they stay in the database)."""
    s.execute(delete(WeeklyReview))
    s.execute(delete(Process))
    blocked = [a for a in AUDIENCES if a not in audiences_of(tag)]
    if blocked:
        s.execute(update(Question).where(Question.audience.in_(blocked)).values(answer={}))


def scrub_removed(s: Session, tags: set[str], derived: bool = False) -> None:
    """Rows with these tags were removed from the app, so text built from them may quote what is gone: the answers stored for every audience that could see them are emptied, and with
    `derived` the weekly reviews and process evidence (both are built again by the next job)."""
    if derived:
        s.execute(delete(WeeklyReview))
        s.execute(delete(Process))
    seen_by = set().union(*(audiences_of(t) for t in tags)) if tags else set()
    if seen_by:
        s.execute(update(Question).where(Question.audience.in_(seen_by)).values(answer={}))


def restore(s: Session, source_id: int) -> int:
    """Put back the tag each row would have in an open source, for the rows that still hold the tag the restriction gave them, and forget the save. A row whose tag moved since
    keeps the tag it has (it was narrowed by a re import or a new line in its file, and that must not be undone). Documents are marked as changed, so the next read works each
    tag out again from the file. Tasks and decisions of a meeting follow the meeting. Returns how many rows were changed."""
    saved = _load(s, source_id)
    changed = 0
    moved: dict[int, tuple[str, str]] = {}  # meeting id: (tag before, tag after)
    everything = _rows(s, source_id)
    for kind in ("m", "d", "t", "x"):
        rows = everything[kind]
        recs = saved.get(kind, {})
        for r in rows:
            rec = recs.get(str(r.id))
            before = r.tag
            if rec:
                own, given = rec[0], rec[1] if len(rec) > 1 else ""
                if own and r.tag != own and (not given or r.tag == given):
                    r.tag, changed = own, changed + 1
            elif kind in {"t", "x"} and r.meeting_id in moved and r.tag == moved[r.meeting_id][0]:
                r.tag, changed = moved[r.meeting_id][1], changed + 1  # made after the source was restricted: it follows its meeting
            if kind == "m" and r.tag != before:
                moved[r.id] = (before, r.tag)
            if kind == "d":
                r.content_hash = RETAGGED  # whatever the file says now is worked out again at the next read
                for c in r.chunks:
                    c.tag = r.tag
    set_state(s, _key(source_id), "")
    search.clear_cache()
    s.flush()
    return changed
