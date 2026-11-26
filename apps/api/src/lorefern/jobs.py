"""Background jobs: read new meetings, detect stuck work and processes, draft reminders, build the weekly review on Mondays."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from lorefern import review, world
from lorefern.context import Ctx
from lorefern.models import WeeklyReview
from sendora_core.events import record_event
from sendora_core.jobs import Handler, enqueue

INTERVALS = {"read": 120, "review": 3600}


def job_read(session: Session, ctx: Ctx) -> dict:
    return world.process_new(session, ctx)


def job_review(session: Session, ctx: Ctx) -> dict:
    """Build the review for last week once, for both scopes, on or after the configured weekday."""
    today = ctx.today(session)
    if today.weekday() < ctx.settings.weekly_review_weekday:
        return {"built": 0}
    ws = review.week_start_of(today)
    built = 0
    for scope in review.SCOPES:
        if session.scalar(select(WeeklyReview.id).where(WeeklyReview.week_start == ws - __import__("datetime").timedelta(days=7), WeeklyReview.scope_tag == scope)) is None:
            review.generate(session, ctx, ws, scope)
            built += 1
    return {"built": built}


JOBS = {"read": job_read, "review": job_review}


def make_handlers(ctx: Ctx) -> dict[str, Handler]:
    return {kind: (lambda session, payload, fn=fn: fn(session, ctx)) for kind, fn in JOBS.items()}


def schedule_due(session: Session, ctx: Ctx) -> int:
    from sendora_core.db import utcnow
    from sendora_core.models import Job

    n, now = 0, utcnow()
    for kind, secs in INTERVALS.items():
        last = session.scalars(select(Job).where(Job.kind == kind).order_by(Job.id.desc())).first()
        if last is None:
            enqueue(session, kind)
            n += 1
        elif last.status in {"done", "failed"} and last.finished_at is not None and (now - last.finished_at.replace(tzinfo=now.tzinfo)).total_seconds() >= secs:
            enqueue(session, kind)
            n += 1
    return n


def run_cycle(session: Session, ctx: Ctx) -> dict:
    out = {"read": job_read(session, ctx), "review": job_review(session, ctx)}
    record_event(session, "cycle.ran", None, None, {})
    return out
