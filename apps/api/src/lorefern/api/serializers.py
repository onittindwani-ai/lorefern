from __future__ import annotations

from datetime import date, datetime


def iso(v: datetime | date | None) -> str | None:
    return v.isoformat() if v else None


def task_dict(t, names: dict[int, str]) -> dict:
    return {"id": t.id, "title": t.title, "owner_id": t.owner_id, "owner": names.get(t.owner_id, "") if t.owner_id else (t.owner_raw or ""), "owner_known": t.owner_id is not None, "due_on": iso(t.due_on), "due_raw": t.due_raw,
            "status": t.status, "confidence": round(t.confidence, 2), "quote": t.quote, "quote_start": t.quote_start, "meeting_id": t.meeting_id, "tag": t.tag, "process_key": t.process_key,
            "blocked_reason": t.blocked_reason, "created_at": iso(t.created_at), "updated_at": iso(t.updated_at), "done_at": iso(t.done_at)}


def decision_dict(d) -> dict:
    return {"id": d.id, "title": d.title, "decided_on": iso(d.decided_on), "decided_by": d.decided_by, "why": d.why, "quote": d.quote, "quote_start": d.quote_start, "meeting_id": d.meeting_id, "status": d.status, "tag": d.tag}


def doc_dict(d, full: bool = False) -> dict:
    out = {"id": d.id, "title": d.title, "slug": d.slug, "kind": d.kind, "doc_type": d.doc_type, "tag": d.tag, "owner": d.owner, "updated_on": iso(d.updated_on), "review_by": iso(d.review_by),
           "status": d.status, "outdated": d.outdated, "flagged": d.flagged, "path": d.external_id}
    if full:
        out["text"] = d.text
    return out
