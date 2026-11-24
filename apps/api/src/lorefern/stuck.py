"""Stuck work detection: overdue, no update, blocked too long, owner overloaded. Pure rules over the task table, with the evidence in plain words."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from lorefern.models import Owner, Task
from lorefern.tasks import OPEN_STATES
from lorefern.util import aware


@dataclass
class Stuck:
    kind: str  # overdue, no_update, blocked, overloaded, unassigned
    task_id: int | None
    owner: str
    days: int
    evidence: str
    tag: str = "company"
    task_ids: list[int] = field(default_factory=list)


def detect(session: Session, today: date, settings, tags: tuple[str, ...]) -> list[Stuck]:
    out: list[Stuck] = []
    tasks = list(session.scalars(select(Task).where(Task.status.in_(OPEN_STATES), Task.tag.in_(tags))))
    names = {o.id: o.name for o in session.scalars(select(Owner))}
    for t in tasks:
        who = names.get(t.owner_id, "") or t.owner_raw or "nobody"
        last = aware(t.updated_at).date()
        idle = (today - last).days
        if t.due_on and t.due_on < today:
            out.append(Stuck("overdue", t.id, who, (today - t.due_on).days, f"\"{t.title}\" was due {t.due_on.isoformat()} and is still {t.status.replace('_', ' ')}.", t.tag))
        if t.status in {"open", "in_progress"} and idle >= settings.stuck_no_update_days and not (t.due_on and t.due_on < today):
            out.append(Stuck("no_update", t.id, who, idle, f"\"{t.title}\" has had no update for {idle} days.", t.tag))
        if t.status == "blocked" and idle >= settings.stuck_blocked_days:
            out.append(Stuck("blocked", t.id, who, idle, f"\"{t.title}\" has been blocked for {idle} days" + (f": {t.blocked_reason}." if t.blocked_reason else "."), t.tag))
        if t.owner_id is None:
            out.append(Stuck("unassigned", t.id, "nobody", (today - aware(t.created_at).date()).days, f"\"{t.title}\" has no owner.", t.tag))
    per: dict[str, list[Task]] = {}
    for t in tasks:
        if t.owner_id:
            per.setdefault(names[t.owner_id], []).append(t)
    horizon = today + timedelta(days=7)
    for who, ts in per.items():
        soon = [t for t in ts if t.due_on and t.due_on <= horizon]
        if len(ts) >= settings.overload_open_tasks or len(soon) >= settings.overload_due_soon:
            ids = ", ".join(str(t.id) for t in ts[:12])
            out.append(Stuck("overloaded", None, who, len(ts), f"{who} holds {len(ts)} open tasks, {len(soon)} due within 7 days (tasks {ids}).", tag=max((t.tag for t in ts), key=lambda x: ("company", "clients", "finance", "people", "leadership").index(x)), task_ids=[t.id for t in ts[:12]]))
    return out
