"""The task store. Meetings produce PROPOSED tasks only. A person approves each one, and every change can be undone with its event log."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from lorefern.actions import DecisionProposal, extract_actions, extract_decisions, validate_quote
from lorefern.models import Decision, Meeting, Owner, Task, TaskEvent
from lorefern.textproc import stems
from sendora_core.audit import record_audit
from sendora_core.events import record_event

OPEN_STATES = ("open", "in_progress", "blocked")


class TaskError(ValueError):
    pass


def _ev(session: Session, task: Task, kind: str, actor: str, now: datetime, note: str = "") -> None:
    task.updated_at = now
    session.add(TaskEvent(task_id=task.id, kind=kind, note=note[:500], actor=actor, at=now))
    session.flush()


def owners_by_name(session: Session) -> dict[str, Owner]:
    return {o.name: o for o in session.scalars(select(Owner))}


def propose_from_meeting(session: Session, meeting: Meeting, now: datetime, with_tasks: bool = True, proposer=None) -> dict:
    """Read the transcript and store proposals. Quotes are re checked here against the stored transcript text. Nothing is approved.
    `proposer` is an optional model reader with the same shape as the rules reader (`model_tasks.ModelProposer`); the checks and the `proposed` status do not depend on who read."""
    text = meeting.transcript.text if meeting.transcript else ""
    owners = list(session.scalars(select(Owner)))
    by_name = {o.name: o for o in owners}
    from lorefern.actions import OwnerBook

    book = OwnerBook(owners)
    if proposer is not None:
        actions, flagged, model_decisions = proposer(text, meeting.held_on, owners)
    else:
        actions, flagged = extract_actions(text, meeting.held_on, owners)
        model_decisions = None
    new_tasks = new_dec = 0
    for a in (actions if with_tasks else []):
        if not validate_quote(text, a.quote, a.quote_start):
            continue
        if _overlaps(session, Task, meeting.id, a.quote_start, a.quote):
            continue
        full = book.resolve(a.owner_name) if a.owner_name else None
        t = Task(title=a.title, owner_id=by_name[full].id if full else None, owner_raw="" if full else a.owner_name, due_on=a.due_on, due_raw=a.due_raw, status="proposed", confidence=a.confidence,
                 quote=a.quote, quote_start=a.quote_start, meeting_id=meeting.id, tag=meeting.tag, created_at=now, updated_at=now)
        session.add(t)
        session.flush()
        _ev(session, t, "created", "lorefern", now, "Proposed from " + meeting.title)
        new_tasks += 1
    for d in (model_decisions if model_decisions is not None else extract_decisions(text, owners)):
        if not validate_quote(text, d.quote, d.quote_start):
            continue
        if _overlaps(session, Decision, meeting.id, d.quote_start, d.quote):
            continue
        session.add(_decision_row(d, meeting))
        new_dec += 1
    meeting.extracted = True
    meeting.flagged_lines = sorted(set(list(meeting.flagged_lines or []) + flagged))
    session.flush()
    record_event(session, "meeting.extracted", "meeting", meeting.id, {"tasks": new_tasks, "decisions": new_dec, "flagged": len(meeting.flagged_lines)})
    return {"tasks": new_tasks, "decisions": new_dec, "flagged": len(meeting.flagged_lines)}


def _overlaps(session: Session, model, meeting_id: int, start: int, quote: str) -> bool:
    """A stored task or decision from the same meeting whose quote covers part of the same characters means this one is already known."""
    for qs, q in session.execute(select(model.quote_start, model.quote).where(model.meeting_id == meeting_id)):
        if qs >= 0 and qs < start + len(quote) and start < qs + len(q):
            return True
    return False


def _decision_row(d: DecisionProposal, meeting: Meeting) -> Decision:
    who = d.decided_by + (f" (agreed: {', '.join(d.agreed_by)})" if d.agreed_by else "")
    return Decision(title=d.title, decided_on=meeting.held_on, decided_by=who, why=d.why, quote=d.quote, quote_start=d.quote_start, meeting_id=meeting.id, status="proposed",
                    tag=meeting.tag, stems=" ".join(stems(d.title + " " + d.why)))


def approve(session: Session, task: Task, actor: str, now: datetime, owner_id: int | None = None, due_on: date | None = None, title: str | None = None) -> Task:
    if task.status != "proposed":
        raise TaskError("Only a proposed task can be approved.")
    if owner_id is not None:
        if session.get(Owner, owner_id) is None:
            raise TaskError("That owner does not exist.")
        task.owner_id, task.owner_raw = owner_id, ""
    if due_on is not None:
        task.due_on = due_on
    if title:
        task.title = title[:300]
    task.status = "open"
    _ev(session, task, "approved", actor, now, "from:proposed")
    record_audit(session, actor, "task.approve", f"task:{task.id}", {"owner": task.owner_id, "due": str(task.due_on)})
    return task


def reject(session: Session, task: Task, actor: str, now: datetime, reason: str = "") -> Task:
    if task.status != "proposed":
        raise TaskError("Only a proposed task can be rejected.")
    task.status = "rejected"
    _ev(session, task, "rejected", actor, now, "from:proposed " + reason)
    record_audit(session, actor, "task.reject", f"task:{task.id}", {"reason": reason[:200]})
    return task


def set_status(session: Session, task: Task, new: str, actor: str, now: datetime, note: str = "") -> Task:
    allowed = {"open": {"in_progress", "blocked", "done"}, "in_progress": {"open", "blocked", "done"}, "blocked": {"open", "in_progress", "done"}, "done": {"open"}}
    if new not in allowed.get(task.status, set()):
        raise TaskError(f"A {task.status} task cannot move to {new}.")
    prev = task.status
    task.status = new
    if new == "blocked":
        task.blocked_reason = note[:300]
    elif prev == "blocked":
        task.blocked_reason = ""
    task.done_at = now if new == "done" else None
    _ev(session, task, {"done": "done", "blocked": "blocked", "open": "reopened"}.get(new, "update"), actor, now, f"from:{prev} {note}".strip())
    record_audit(session, actor, f"task.{new}", f"task:{task.id}", {"from": prev})
    return task


def add_update(session: Session, task: Task, actor: str, now: datetime, note: str) -> Task:
    if task.status not in OPEN_STATES:
        raise TaskError("Only an active task takes an update.")
    _ev(session, task, "update", actor, now, note)
    return task


def reassign(session: Session, task: Task, owner_id: int | None, actor: str, now: datetime) -> Task:
    if owner_id is not None and session.get(Owner, owner_id) is None:
        raise TaskError("That owner does not exist.")
    old = task.owner_id
    task.owner_id = owner_id
    _ev(session, task, "edited", actor, now, f"owner:{old}->{owner_id}")
    record_audit(session, actor, "task.reassign", f"task:{task.id}", {"from": old, "to": owner_id})
    return task


def undo_last(session: Session, task: Task, actor: str, now: datetime) -> Task:
    """Undo the last approve, reject, done, blocked or reopen: put the task back to the state the event recorded."""
    for e in reversed(task.events):
        if e.kind in {"approved", "rejected", "done", "blocked", "reopened"} and e.note.startswith("from:"):
            prev = e.note.split()[0][5:]
            task.status = prev
            task.done_at = None
            if e.kind == "blocked":
                task.blocked_reason = ""
            session.delete(e)
            session.flush()
            session.expire(task, ["events"])
            task.updated_at = now
            session.add(TaskEvent(task_id=task.id, kind="update", note=f"Undid {e.kind}", actor=actor, at=now))
            record_audit(session, actor, "task.undo", f"task:{task.id}", {"undid": e.kind, "back_to": prev})
            return task
    raise TaskError("Nothing to undo on this task.")
