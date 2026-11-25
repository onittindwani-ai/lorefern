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


def _repo_data() -> Path | None:
    """The data folder next to the code, found only in a source checkout. An installed copy (the Docker image, a wheel) has no such folder, so SEED_DIR is the first choice and this
    is the last resort, and a path that is too short to have a parent is not an error."""
    try:
        return Path(__file__).resolve().parents[4] / "data"
    except IndexError:
        return None


REPO_DATA = _repo_data()


class SourceError(ValueError):
    """A source cannot be read as set up. The message is plain words with no secret in it."""


def seed_dir(ctx) -> Path:
    """The demo data folder: SEED_DIR first (with its `seed` sub folder when there is one), otherwise the checkout's data folder."""
    base = Path(ctx.settings.seed_dir) if ctx.settings.seed_dir else REPO_DATA
    if base is None:
        raise FileNotFoundError("The demo data folder was not found. Set SEED_DIR to the data folder of the repository.")
    return base / "seed" if (base / "seed").is_dir() else base


def check_seed(ctx) -> Path:
    """The demo data folder, checked BEFORE anything is erased: a missing folder must leave the database as it is."""
    root = seed_dir(ctx)
    missing = [n for n in ("owners.json", "tasks.json", "slack_channels.json") if not (root / n).is_file()] + [n for n in ("company", "meetings", "slack") if not (root / n).is_dir()]
    if missing:
        raise FileNotFoundError(f"The demo data folder {root} is missing {', '.join(missing)}. Set SEED_DIR to the data folder of the repository.")
    return root


def knowledge_base(ctx) -> Path:
    """The folder every folder and Slack source lives in: KNOWLEDGE_DIR, or the demo seed folder while only a demo is running."""
    if ctx.settings.knowledge_dir:
        return Path(ctx.settings.knowledge_dir).resolve()
    if ctx.settings.demo_mode:
        return seed_dir(ctx).resolve()
    raise SourceError("KNOWLEDGE_DIR is empty. Set it to the folder that holds your documents.")


def source_root(ctx, src: Source) -> Path:
    """Where a folder or Slack source reads from: its own path inside the knowledge folder, and never anything outside it. The one place both the Sources page and the hourly worker ask."""
    base = knowledge_base(ctx)
    target = (base / src.uri).resolve() if src.uri else base
    if target != base and base not in target.parents:
        raise SourceError("The path must be inside the knowledge folder.")
    if not target.exists():
        raise SourceError(f"Nothing was found at \"{src.uri or '.'}\" inside the knowledge folder. Check the path on this source.")
    return target


def nested_roots(session: Session, ctx, src: Source, root: Path) -> tuple[Path, ...]:
    """Folders of other folder sources that sit inside this source's folder. Each belongs to its own source and tag, so this source's read leaves them alone."""
    out = []
    for other in session.scalars(select(Source).where(Source.kind == "folder", Source.id != src.id, Source.uri != "")):
        try:
            p = source_root(ctx, other)
        except SourceError:
            continue
        if p != root and root in p.parents:
            out.append(p)
    return tuple(out)


def remote_scope(src: Source) -> list[str] | None:
    """The Drive folder ids or Notion page ids a source is limited to (its `uri`, separated by commas), or None for 'everything the credential can read'."""
    ids = [x.strip() for x in (src.uri or "").split(",") if x.strip()]
    return ids or None


def incomplete_note(counts: dict) -> str:
    """What the Sources page says after a read that stopped early (a limit, or a file that could not be read): nothing was removed from the index. Empty after a complete read."""
    if counts.get("incomplete") or counts.get("truncated"):
        return "The last read stopped before it saw everything, so nothing was removed from the index. Read it again, and see the limits in docs/13."
    return ""


def read_source(session: Session, ctx, src: Source) -> dict:
    """Read one source again, by kind, and return the counts. The Sources page and the worker both call this, so they cannot disagree about what a source contains."""
    if src.kind == "folder":
        root = source_root(ctx, src)
        return ingest.ingest_folder(session, src, root, ctx.today(session), exclude=nested_roots(session, ctx, src, root))
    if src.kind in {"drive", "notion"}:
        if ctx.settings.knowledge_adapter != src.kind:
            raise SourceError(f"KNOWLEDGE_ADAPTER is {ctx.settings.knowledge_adapter}, so this {src.kind} source cannot be read. Set KNOWLEDGE_ADAPTER={src.kind}.")
        return ingest.ingest_remote(session, src, ctx.adapters.knowledge.list_documents(remote_scope(src)), ctx.today(session))
    if src.kind == "slack":
        target = source_root(ctx, src)
        base = knowledge_base(ctx)
        mapping = next((m for m in (target / "slack_channels.json", base / "slack_channels.json") if m.is_file()), None)
        tags = json.loads(mapping.read_text()) if mapping else {}
        return ingest.ingest_slack(session, src, read_export(target), tags, ctx.today(session))
    return ingest.sync_meetings(session, ctx, ctx.today(session))


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
    """Re read folder, Drive and Notion sources that were last read more than an hour ago, each from its own folder or ids."""
    from datetime import timedelta

    now = ctx.now(session)
    for src in session.scalars(select(Source).where(Source.kind.in_(("folder", "drive", "notion")))):
        if src.last_synced_at and (now - src.last_synced_at.replace(tzinfo=now.tzinfo)) < timedelta(seconds=every_s):
            continue
        try:
            if src.kind == "folder" and not ctx.settings.knowledge_dir:
                continue
            res = read_source(session, ctx, src)
            src.last_synced_at, src.status, src.error = now, "ready", incomplete_note(res)
        except SourceError as exc:
            src.status, src.error = "error", str(exc)
        except Exception as exc:  # a broken source must not stop the other jobs
            src.status, src.error = "error", f"{type(exc).__name__}: could not read this source."
