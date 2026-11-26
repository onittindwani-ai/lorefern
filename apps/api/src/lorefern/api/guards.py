"""One way to load a row for a person: the row exists AND the person's audience may see its tag. Anything else answers 404 with the same words, so a change request
cannot be used to find out that a restricted row exists."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from lorefern.models import Document, Source, Task
from lorefern.visibility import allowed_tags


def visible_or_404(s: Session, model, row_id: int, audience: str, noun: str):
    row = s.get(model, row_id)
    if row is None or getattr(row, "tag", None) not in allowed_tags(audience):
        raise HTTPException(404, f"No such {noun}.")
    return row


def hidden_source_ids(s: Session, ids: set[int], audience: str) -> set[int]:
    """The sources among `ids` that this audience cannot see: the source's own tag is not theirs and none of its documents is either (the same rule the Sources page uses)."""
    tags = allowed_tags(audience)
    out = set()
    for src in s.scalars(select(Source).where(Source.id.in_(ids))) if ids else []:
        if src.default_tag not in tags and s.scalar(select(Document.id).where(Document.source_id == src.id, Document.tag.in_(tags)).limit(1)) is None:
            out.add(src.id)
    return out | {i for i in ids if s.get(Source, i) is None}  # an entry about a source that is gone tells nothing a reader needs


def approval_visible(s: Session, approval, audience: str) -> bool:
    """An approval to send reminders is only for people who may see every task those reminders are about. Other approvals are visible to anyone who may see approvals at all."""
    if approval.action != "reminders.send":
        return True
    from lorefern.models import Reminder

    tags = allowed_tags(audience)
    for rid in approval.payload.get("ids", []):
        r = s.get(Reminder, int(rid))
        t = s.get(Task, r.task_id) if r is not None else None
        if t is None or t.tag not in tags:
            return False
    return True
