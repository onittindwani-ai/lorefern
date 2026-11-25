"""What a document gets when nobody labelled it.

A document, transcript or Slack channel with no tag of its own, no tag on its folder and no tag from its source is given the NARROWEST tag (owner only with the default audience map),
never `company`. The owner can choose another tag for one source on purpose, for example "everything in this Drive folder is company material". The choice is stored in the state
table, shown on the Sources page and written to the audit log. It applies at the next read of the source.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from lorefern.models import TAGS, State


def _key(source_id: int) -> str:
    return f"untagged:{source_id}"


def get(session: Session, source_id: int | None) -> str:
    """The tag chosen for unlabelled items of this source, or an empty string (which means the narrowest tag)."""
    if source_id is None:
        return ""
    row = session.get(State, _key(source_id))
    value = (row.value if row else "").strip().lower()
    return value if value in TAGS else ""


def put(session: Session, source_id: int, tag: str) -> None:
    if tag and tag not in TAGS:
        raise ValueError("Unknown visibility tag.")
    row = session.get(State, _key(source_id))
    if row is None:
        session.add(State(key=_key(source_id), value=tag))
    else:
        row.value = tag
    session.flush()
