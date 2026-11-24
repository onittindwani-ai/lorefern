"""Load the demo world: owners, the company folder, a Slack export, meeting transcripts, planted tasks and their decisions. Fictional, offline."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from lorefern import ingest, search, tasks
from lorefern.adapters.meetings import load_transcript_file, visibility_of
from lorefern.adapters.slack import read_export
from lorefern.models import Meeting, Owner, Source, Task, TaskEvent

PROCESSED = 11  # meetings m01 to m11 are already worked through, m12 is left for the live demo


def seed_dir(ctx) -> Path:
    return Path(ctx.settings.seed_dir or "data") / "seed" if (Path(ctx.settings.seed_dir or "data") / "seed").exists() else Path(ctx.settings.seed_dir or "data")


def load_world(session: Session, ctx) -> dict:
    root = seed_dir(ctx)
    now = ctx.now(session)
    today = now.date()
    for o in json.loads((root / "owners.json").read_text()):
        session.add(Owner(**o))
    session.flush()
    folder = Source(kind="folder", name="Company folder", uri="company", default_tag="company", reliability="B", owner="Priya Nair", status="ready", last_synced_at=now)
    slack = Source(kind="slack", name="Slack export", uri="slack", default_tag="company", reliability="B", owner="Priya Nair", status="ready", last_synced_at=now)
    meet = Source(kind="meetings", name="Meeting transcripts", uri="meetings", default_tag="company", reliability="A", owner="Priya Nair", status="ready", last_synced_at=now)
    session.add_all([folder, slack, meet])
    session.flush()
    docs = ingest.ingest_folder(session, folder, root / "company", today)
    channel_tags = json.loads((root / "slack_channels.json").read_text())
    days = ingest.ingest_slack(session, slack, read_export(root / "slack"), channel_tags, today)
    meetings = {}
    for p in sorted((root / "meetings").glob("*.txt")):
        m, _ = ingest.ingest_meeting(session, meet, load_transcript_file(p), today, visibility_of(p))
        meetings[p.stem] = m
    search.rebuild(session)
    by_name = {o.name: o for o in session.scalars(select(Owner))}
    n_tasks = 0
    for row in json.loads((root / "tasks.json").read_text()):
        updated = now - timedelta(days=row["idle_days"])
        mt = meetings.get(row["meeting"]) if row["meeting"] else None
        created = datetime.combine(mt.held_on, datetime.min.time(), tzinfo=now.tzinfo) + timedelta(hours=10) if mt else now - timedelta(days=row["idle_days"] + 14)
        t = Task(title=row["title"], owner_id=by_name[row["owner"]].id if row["owner"] else None, due_on=date.fromisoformat(row["due"]) if row["due"] else None, status=row["status"], confidence=0.9 if mt else 1.0,
                 quote=row["quote"], quote_start=row["quote_start"], meeting_id=mt.id if mt else None, tag=row["tag"], process_key=row.get("process", ""), blocked_reason=row.get("blocked_reason", ""),
                 created_at=created, updated_at=updated, done_at=updated if row["status"] == "done" else None)
        session.add(t)
        session.flush()
        session.add(TaskEvent(task_id=t.id, kind="created", note="Seed", actor="lorefern", at=created))
        session.add(TaskEvent(task_id=t.id, kind="approved", note="from:proposed", actor="priya@pinegate.example.test", at=created + timedelta(hours=1)))
        if updated > created + timedelta(hours=2):
            session.add(TaskEvent(task_id=t.id, kind="update" if row["status"] != "done" else "done", note=row.get("blocked_reason", "") or "Seed update", actor=row["owner"] or "lorefern", at=updated))
        n_tasks += 1
    n_dec = 0
    for stem_, m in sorted(meetings.items()):
        if int(stem_[1:3]) <= PROCESSED:
            r = tasks.propose_from_meeting(session, m, now, with_tasks=False, proposer=ctx.proposer(session))  # these meetings were worked through already: their approved tasks are the planted ones
            n_dec += r["decisions"]
    from lorefern.models import Decision

    for d in session.scalars(select(Decision)):
        d.status = "confirmed"
    session.flush()
    return {"documents": docs, "slack_days": days["new"], "meetings": len(meetings), "planted_tasks": n_tasks, "decisions": n_dec}


def process_new(session: Session, ctx) -> dict:
    """Run the extraction on every meeting not yet read, detect processes, draft reminders and refresh the review."""
    from lorefern import reminders, review, sops

    now = ctx.now(session)
    proposed = decisions = 0
    if not ctx.settings.demo_mode:
        ingest.sync_meetings(session, ctx, ctx.today(session))
        _sync_sources(session, ctx)
    proposer = ctx.proposer(session)
    for m in session.scalars(select(Meeting).where(Meeting.extracted.is_(False))):
        r = tasks.propose_from_meeting(session, m, now, proposer=proposer)
        proposed += r["tasks"]
        decisions += r["decisions"]
    procs = len(sops.detect(session, ctx.today(session), ctx.settings, wording=ctx.wording(session)))
    drafted = reminders.plan(session, ctx.today(session), ctx.settings)
    return {"proposed_tasks": proposed, "proposed_decisions": decisions, "processes": procs, "reminders": drafted}


def _sync_sources(session: Session, ctx, every_s: int = 3600) -> None:
    """Re read folder, Drive and Notion sources that were last read more than an hour ago."""
    from datetime import timedelta
    from pathlib import Path

    from lorefern.models import Source

    now = ctx.now(session)
    for src in session.scalars(select(Source).where(Source.kind.in_(("folder", "drive", "notion")))):
        if src.last_synced_at and (now - src.last_synced_at.replace(tzinfo=now.tzinfo)) < timedelta(seconds=every_s):
            continue
        try:
            if src.kind == "folder":
                if not ctx.settings.knowledge_dir:
                    continue
                ingest.ingest_folder(session, src, Path(ctx.settings.knowledge_dir), ctx.today(session))
            else:
                ingest.ingest_remote(session, src, ctx.adapters.knowledge.list_documents(), ctx.today(session))
            src.last_synced_at, src.status, src.error = now, "ready", ""
        except Exception as exc:  # a broken source must not stop the other jobs
            src.status, src.error = "error", f"{type(exc).__name__}: could not read this source."
