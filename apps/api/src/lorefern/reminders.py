"""Task reminders. Planning writes drafts to the database. Sending goes through the email adapter, which refuses in draft mode and when the kill switch is on."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from lorefern.models import Owner, Reminder, Task
from lorefern.tasks import OPEN_STATES
from sendora_core.safety import guard_write


def plan(session: Session, today: date, settings) -> int:
    """Draft one reminder per task and kind per day: due tomorrow, overdue (every third day), no update. Only on working days."""
    days = {d.strip().lower()[:3] for d in settings.working_days.split(",")}
    if today.strftime("%a").lower() not in days:
        return 0
    made = 0
    for t in session.scalars(select(Task).where(Task.status.in_(OPEN_STATES), Task.owner_id.is_not(None))):
        kind = ""
        if t.due_on == today + timedelta(days=1):
            kind = "due_soon"
        elif t.due_on and t.due_on < today and (today - t.due_on).days % 3 == 0:
            kind = "overdue"
        if not kind:
            continue
        if session.scalar(select(Reminder.id).where(Reminder.task_id == t.id, Reminder.kind == kind, Reminder.on_date == today)):
            continue
        o = session.get(Owner, t.owner_id)
        line = {"due_soon": f"Task '{t.title}' is due tomorrow ({t.due_on}).", "overdue": f"Task '{t.title}' was due {t.due_on} and is still open."}[kind]
        session.add(Reminder(task_id=t.id, kind=kind, on_date=today, body=f"Hi {o.name.split()[0]}, {line} Reply with an update or move the date."))
        made += 1
    session.flush()
    return made


def send(session: Session, settings, email, reminder_ids: list[int]) -> int:
    guard_write(settings, "reminders.send")
    n = 0
    for r in session.scalars(select(Reminder).where(Reminder.id.in_(reminder_ids), Reminder.status == "drafted")):
        o = session.get(Owner, session.get(Task, r.task_id).owner_id)
        if o and o.email:
            email.send(to=o.email, subject="Task reminder", body=r.body)
            r.status = "sent"
            n += 1
    return n
