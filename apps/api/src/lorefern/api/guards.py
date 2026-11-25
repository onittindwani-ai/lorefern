"""One way to load a row for a person: the row exists AND the person's audience may see its tag. Anything else answers 404 with the same words, so a change request
cannot be used to find out that a restricted row exists."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from lorefern.visibility import allowed_tags


def visible_or_404(s: Session, model, row_id: int, audience: str, noun: str):
    row = s.get(model, row_id)
    if row is None or getattr(row, "tag", None) not in allowed_tags(audience):
        raise HTTPException(404, f"No such {noun}.")
    return row
