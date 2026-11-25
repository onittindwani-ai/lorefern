"""Write routes. Every one needs an owner or leadership audience, records an audit entry, and can be undone where it makes sense. Nothing leaves the system."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from lorefern import ingest, reminders, review, search, sops, source_tags, tasks, untagged, world
from lorefern.adapters.meetings import meeting_from_file
from lorefern.api.deps import db, get_ctx, owner_write, writer
from lorefern.api.guards import visible_or_404
from lorefern.context import Ctx
from lorefern.models import Decision, Meeting, Owner, Reminder, Source, Task
from lorefern.visibility import TAGS, allowed_tags, narrowest_tag
from sendora_core.adapters import AdapterError
from sendora_core.approvals import request_approval
from sendora_core.audit import record_audit
from sendora_core.models import Approval

router = APIRouter(prefix="/api", tags=["write"])


def _task(s: Session, tid: int, u: dict) -> Task:
    """A task the signed in person may see. A task they may not see answers exactly like one that does not exist."""
    return visible_or_404(s, Task, tid, u["audience"], "task")


def _wrap(fn, *a, **k):
    try:
        return fn(*a, **k)
    except tasks.TaskError as exc:
        raise HTTPException(409, str(exc)) from exc


class ApproveIn(BaseModel):
    owner_id: int | None = None
    due_on: date | None = None
    title: str | None = Field(default=None, max_length=300)


@router.post("/tasks/{tid}/approve", summary="Approve a proposed task. Only a person can turn a proposal into a task.")
def approve(tid: int, b: ApproveIn, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    t = _wrap(tasks.approve, s, _task(s, tid, u), u["user"], ctx.now(s), b.owner_id, b.due_on, b.title)
    return {"id": t.id, "status": t.status}


class BulkIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)


@router.post("/tasks/bulk-approve", summary="Approve several proposals at once, each one still checked on its own")
def bulk_approve(b: BulkIn, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    done, skipped = [], []
    seen = allowed_tags(u["audience"])
    for tid in b.ids:
        t = s.get(Task, tid)
        try:
            if t is None or t.tag not in seen:  # a hidden task is skipped exactly like a missing one
                raise tasks.TaskError("missing")
            tasks.approve(s, t, u["user"], ctx.now(s))
            done.append(tid)
        except tasks.TaskError:
            skipped.append(tid)
    return {"approved": done, "skipped": skipped}


class RejectIn(BaseModel):
    reason: str = Field(default="", max_length=300)


@router.post("/tasks/{tid}/reject", summary="Reject a proposed task")
def reject(tid: int, b: RejectIn, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    t = _wrap(tasks.reject, s, _task(s, tid, u), u["user"], ctx.now(s), b.reason)
    return {"id": t.id, "status": t.status}


class StatusIn(BaseModel):
    status: str
    note: str = Field(default="", max_length=300)


@router.post("/tasks/{tid}/status", summary="Move a task: in progress, blocked (with a reason), done, or open again")
def status(tid: int, b: StatusIn, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    if b.status == "blocked" and not b.note.strip():
        raise HTTPException(422, "Say what the task is blocked by.")
    t = _wrap(tasks.set_status, s, _task(s, tid, u), b.status, u["user"], ctx.now(s), b.note)
    return {"id": t.id, "status": t.status}


class NoteIn(BaseModel):
    note: str = Field(min_length=1, max_length=400)


@router.post("/tasks/{tid}/update", summary="Add a progress update")
def update(tid: int, b: NoteIn, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    _wrap(tasks.add_update, s, _task(s, tid, u), u["user"], ctx.now(s), b.note)
    return {"ok": True}


class ReassignIn(BaseModel):
    owner_id: int | None


@router.post("/tasks/{tid}/reassign", summary="Change the owner")
def reassign(tid: int, b: ReassignIn, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    t = _wrap(tasks.reassign, s, _task(s, tid, u), b.owner_id, u["user"], ctx.now(s))
    return {"id": t.id, "owner_id": t.owner_id}


@router.post("/tasks/{tid}/undo", summary="Undo the last approve, reject, done, blocked or reopen on this task")
def undo(tid: int, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    t = _wrap(tasks.undo_last, s, _task(s, tid, u), u["user"], ctx.now(s))
    return {"id": t.id, "status": t.status}


class NewTask(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    owner_id: int | None = None
    due_on: date | None = None
    tag: str = "company"


@router.post("/tasks", summary="Add a task by hand (it starts open, because a person wrote it)")
def create_task(b: NewTask, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    if b.tag not in TAGS:
        raise HTTPException(422, "Unknown visibility tag.")
    if b.tag not in allowed_tags(u["audience"]):
        raise HTTPException(422, "You cannot give a task a visibility tag that you cannot see yourself.")
    now = ctx.now(s)
    t = Task(title=b.title, owner_id=b.owner_id, due_on=b.due_on, status="open", tag=b.tag, created_at=now, updated_at=now)
    s.add(t)
    s.flush()
    tasks._ev(s, t, "created", u["user"], now, "Added by hand")
    record_audit(s, u["user"], "task.create", f"task:{t.id}", {"tag": b.tag})
    return {"id": t.id}


def _decision(s: Session, did: int, u: dict) -> Decision:
    return visible_or_404(s, Decision, did, u["audience"], "decision")


@router.post("/decisions/{did}/confirm", summary="Confirm a proposed decision so it enters the decision log")
def confirm(did: int, s: Session = Depends(db), u: dict = Depends(writer)):
    d = _decision(s, did, u)
    if d.status != "proposed":
        raise HTTPException(409, "Only a proposed decision can be confirmed.")
    d.status = "confirmed"
    record_audit(s, u["user"], "decision.confirm", f"decision:{d.id}", {})
    return {"id": d.id, "status": d.status}


@router.post("/decisions/{did}/reject", summary="Reject a proposed decision")
def reject_decision(did: int, s: Session = Depends(db), u: dict = Depends(writer)):
    d = _decision(s, did, u)
    if d.status != "proposed":
        raise HTTPException(409, "Only a proposed decision can be rejected.")
    d.status = "rejected"
    record_audit(s, u["user"], "decision.reject", f"decision:{d.id}", {})
    return {"id": d.id, "status": d.status}


class MeetingIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    held_on: date
    text: str = Field(min_length=10, max_length=400_000)
    provider: str = "file"
    visibility: str | None = None  # left out means the narrowest tag this person may see


@router.post("/meetings", summary="Import a pasted transcript. It is stored as data and read for proposals, nothing more.")
def import_meeting(b: MeetingIn, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    if b.provider not in {"file", "otter", "meetily", "fireflies", "fathom"}:
        raise HTTPException(422, "Unknown provider name.")
    wanted = (b.visibility or "").strip().lower() or narrowest_tag(u["audience"])
    if wanted not in TAGS or wanted not in allowed_tags(u["audience"]):
        raise HTTPException(422, "Choose a visibility tag from the list that you may see.")
    src = s.scalar(select(Source).where(Source.kind == "meetings").order_by(Source.id))
    if src is None:
        src = Source(kind="meetings", name="Meeting transcripts", default_tag="company", reliability="A", status="ready")
        s.add(src)
        s.flush()
    rm = meeting_from_file(f"{b.title}.txt", b.text, b.provider, b.held_on.isoformat(), b.title)
    digest = hashlib.sha1(f"{b.held_on.isoformat()}|{b.title}|{b.text}".encode()).hexdigest()[:12]  # the same transcript is the same meeting, in every process
    rm.external_id = f"import-{b.held_on.isoformat()}-{digest}"
    if not rm.lines:
        raise HTTPException(422, "No 'Speaker: words' lines were found in the text.")
    m, state = ingest.ingest_meeting(s, src, rm, ctx.today(s), wanted)
    if state == "same":
        raise HTTPException(409, f"This transcript is already imported as {m.title}, held on {m.held_on.isoformat()}.")
    search.rebuild(s)
    found = tasks.propose_from_meeting(s, m, ctx.now(s), proposer=ctx.proposer(s))
    record_audit(s, u["user"], "meeting.import", f"meeting:{m.id}", {"tag": m.tag, "lines": len(rm.lines), **found})
    return {"id": m.id, "state": state, "tag": m.tag, **found}


@router.post("/meetings/{mid}/extract", summary="Read the transcript again and add proposals (nothing is approved)")
def extract(mid: int, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    m = visible_or_404(s, Meeting, mid, u["audience"], "meeting")
    out = tasks.propose_from_meeting(s, m, ctx.now(s), proposer=ctx.proposer(s))
    record_audit(s, u["user"], "meeting.extract", f"meeting:{m.id}", out)
    return out


class ReviewIn(BaseModel):
    scope: str = "company"


@router.post("/reviews/generate", summary="Build the weekly operating review now, for last week")
def generate_review(b: ReviewIn, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    if b.scope not in review.SCOPES or (b.scope == "leadership" and u["audience"] not in {"owner", "leadership"}):
        raise HTTPException(422, "Unknown scope.")
    r = review.generate(s, ctx, review.week_start_of(ctx.today(s)), b.scope)
    record_audit(s, u["user"], "review.generate", f"review:{r.id}", {"scope": b.scope, "claims": r.claims, "linked": r.linked})
    return {"id": r.id, "claims": r.claims, "linked": r.linked}


@router.post("/sops/refresh", summary="Find recurring processes again and match them to SOPs")
def sops_refresh(s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    n = len(sops.detect(s, ctx.today(s), ctx.settings, wording=ctx.wording(s)))
    record_audit(s, u["user"], "sops.refresh", None, {"processes": n})
    return {"processes": n}


class SyncIn(BaseModel):
    default_tag: str | None = None
    untagged_tag: str | None = None  # the tag for items of this source that carry no tag of their own. An empty string goes back to the narrowest tag.


def _read_error(exc: Exception) -> HTTPException:
    return HTTPException(422 if isinstance(exc, world.SourceError) else 502, str(exc))


@router.post("/sources/{sid}/sync", summary="Read the source again. Folder and Slack sources read from this machine.")
def sync_source(sid: int, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(owner_write)):
    src = s.get(Source, sid)
    if src is None:
        raise HTTPException(404, "No such source.")
    try:
        res = world.read_source(s, ctx, src)
    except (world.SourceError, AdapterError, FileNotFoundError) as exc:
        raise _read_error(exc) from exc
    src.last_synced_at, src.status, src.error = ctx.now(s), "ready", ""
    record_audit(s, u["user"], "source.sync", f"source:{sid}", res)
    return res


@router.patch("/sources/{sid}", summary="Change a source's default visibility tag (owner only). Everything made from it is re tagged, and setting it back to company restores the tags it had.")
def retag(sid: int, b: SyncIn, s: Session = Depends(db), u: dict = Depends(owner_write)):
    src = s.get(Source, sid)
    if src is None or (b.default_tag is not None and b.default_tag not in TAGS) or (b.untagged_tag not in (None, "") and b.untagged_tag not in TAGS):
        raise HTTPException(422, "Unknown source or tag.")
    changed = 0
    if b.default_tag and b.default_tag != src.default_tag:
        src.default_tag = b.default_tag
        changed = source_tags.restrict(s, sid, b.default_tag) if b.default_tag != "company" else source_tags.restore(s, sid)
        record_audit(s, u["user"], "source.retag", f"source:{sid}", {"tag": b.default_tag, "changed": changed})
    if b.untagged_tag is not None and b.untagged_tag != untagged.get(s, sid):
        untagged.put(s, sid, b.untagged_tag)
        record_audit(s, u["user"], "source.untagged_tag", f"source:{sid}", {"tag": b.untagged_tag or narrowest_tag()})
    return {"id": src.id, "default_tag": src.default_tag, "untagged_tag": untagged.get(s, sid) or narrowest_tag(), "changed": changed}


@router.post("/reminders/plan", summary="Draft reminders for today. Nothing is sent.")
def plan_reminders(s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    return {"drafted": reminders.plan(s, ctx.today(s), ctx.settings)}


class SendIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=100)


@router.post("/reminders/request-send", summary="Ask for approval to send drafted reminders. Another person must approve.")
def request_send(b: SendIn, s: Session = Depends(db), u: dict = Depends(writer)):
    seen = allowed_tags(u["audience"])
    rows = [r for r in s.scalars(select(Reminder).where(Reminder.id.in_(b.ids), Reminder.status == "drafted")) if (t := s.get(Task, r.task_id)) is not None and t.tag in seen]
    if not rows:
        raise HTTPException(409, "No drafted reminders in that list.")
    waiting = {int(i) for a in s.scalars(select(Approval).where(Approval.action == "reminders.send", Approval.status == "pending")) for i in a.payload.get("ids", [])}
    rows = [r for r in rows if r.id not in waiting]
    if not rows:
        raise HTTPException(409, "Those reminders are already waiting for a second person to approve them.")
    a = request_approval(s, "reminders.send", f"Send {len(rows)} task reminders", {"ids": [r.id for r in rows]}, "low", u["user"])
    return {"approval_id": a.id}


class NewOwner(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    role: str = Field(default="", max_length=120)
    email: str = Field(default="", max_length=254)


@router.post("/owners", summary="Add a person who can own work. Task owners must come from this list.")
def add_owner(b: NewOwner, s: Session = Depends(db), u: dict = Depends(writer)):
    name = " ".join(b.name.split())
    if not any(ch.isalpha() for ch in name):
        raise HTTPException(422, "A name needs at least one letter.")
    if any(o.name.lower() == name.lower() for o in s.scalars(select(Owner))):
        raise HTTPException(409, "There is already a person with that name.")
    o = Owner(name=name, role=b.role.strip(), email=b.email.strip(), aliases=[name.split()[0]])
    s.add(o)
    s.flush()
    record_audit(s, u["user"], "owner.add", f"owner:{o.id}", {"name": name})
    return {"id": o.id, "name": o.name, "role": o.role}


class NewSource(BaseModel):
    kind: str
    name: str = Field(min_length=2, max_length=120)
    default_tag: str = "company"
    uri: str = Field(default="", max_length=300)  # a folder or Slack export path inside KNOWLEDGE_DIR, or comma separated Drive folder ids or Notion page ids
    untagged_tag: str = ""  # the tag for items of this source that carry no tag of their own. Empty means the narrowest tag.


@router.post("/sources", summary="Add a source. A folder or Slack export path is relative to KNOWLEDGE_DIR. Owner only.")
def add_source(b: NewSource, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(owner_write)):
    if b.kind not in {"folder", "slack", "drive", "notion"} or b.default_tag not in TAGS or (b.untagged_tag and b.untagged_tag not in TAGS):
        raise HTTPException(422, "Unknown kind or tag.")
    if b.kind in {"folder", "slack"} and (b.uri.startswith("/") or ".." in Path(b.uri).parts):
        raise HTTPException(422, "The path must be inside KNOWLEDGE_DIR, so it cannot be absolute or contain '..'.")
    if b.kind in {"drive", "notion"} and not re.fullmatch(r"[A-Za-z0-9_,\- ]*", b.uri):
        raise HTTPException(422, "Name Drive folders or Notion pages by their ids, separated by commas.")
    if any(x.name.lower() == b.name.strip().lower() for x in s.scalars(select(Source))):
        raise HTTPException(409, "There is already a source with that name.")
    if b.kind in {"drive", "notion"} and not b.uri.strip() and s.scalar(select(Source.id).where(Source.kind == b.kind, Source.uri == "")):
        raise HTTPException(409, f"There is already a {b.kind} source that reads everything the sign in can reach. Name the folders or pages of this one, so each file belongs to one source and one tag.")
    src = Source(kind=b.kind, name=b.name.strip(), uri=b.uri.strip(), default_tag=b.default_tag, reliability="B", owner="", status="new")
    s.add(src)
    s.flush()
    if b.untagged_tag:
        untagged.put(s, src.id, b.untagged_tag)
    record_audit(s, u["user"], "source.add", f"source:{src.id}", {"kind": b.kind, "tag": b.default_tag, "untagged_tag": b.untagged_tag or narrowest_tag()})
    return {"id": src.id, "kind": src.kind, "name": src.name, "default_tag": src.default_tag}
