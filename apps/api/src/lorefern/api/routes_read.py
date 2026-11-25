"""Read routes. Every query filters on the viewer's allowed tags in the query itself. A restricted row answers 404, the same as a row that does not exist."""

from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lorefern import folder_tool, qa, review, sops, stuck, untagged, world
from lorefern.api.deps import db, get_ctx, real_audience, user, viewer
from lorefern.api.serializers import decision_dict, doc_dict, iso, task_dict
from lorefern.context import Ctx
from lorefern.models import Decision, Document, Meeting, Owner, Question, Reminder, Source, Task
from lorefern.visibility import AUDIENCE_TAGS, allowed_tags, narrowest_tag

router = APIRouter(prefix="/api", tags=["read"])


def _names(s: Session) -> dict[int, str]:
    return {o.id: o.name for o in s.scalars(select(Owner))}


@router.get("/overview", summary="Numbers for the top of every page, counted only over what the viewer may see")
def overview(s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), aud: str = Depends(viewer)):
    tags = allowed_tags(aud)
    count = lambda col, *w: s.scalar(select(func.count()).select_from(col).where(*w)) or 0  # noqa: E731
    st = stuck.detect(s, ctx.today(s), ctx.settings, tags)
    from sendora_core.models import Approval

    return {"audience": aud, "open_tasks": count(Task, Task.status.in_(("open", "in_progress", "blocked")), Task.tag.in_(tags)), "proposed": count(Task, Task.status == "proposed", Task.tag.in_(tags)),
            "stuck": len({x.task_id for x in st if x.task_id}), "documents": count(Document, Document.tag.in_(tags)), "meetings": count(Meeting, Meeting.tag.in_(tags)),
            "decisions": count(Decision, Decision.status == "confirmed", Decision.tag.in_(tags)), "proposed_decisions": count(Decision, Decision.status == "proposed", Decision.tag.in_(tags)),
            "pending_approvals": count(Approval, Approval.status == "pending"), "processes_gap": sum(1 for p in sops.visible(s, aud) if p["coverage"] != "covered"),
            "today": ctx.today(s).isoformat(), "company": ctx.settings.company_name}


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


@router.post("/ask", summary="Ask a question. The answer cites the passages it relies on and refuses what it cannot ground.")
def ask(b: AskIn, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(user), aud: str = Depends(viewer)):
    a = qa.ask(s, ctx, b.question, aud)
    d = a.as_dict()
    s.add(Question(text=b.question, asker=u["user"], audience=aud, outcome=a.outcome, answer=d, asked_at=ctx.now(s)))
    return d


@router.get("/questions", summary="The viewer's own recent questions")
def questions(s: Session = Depends(db), u: dict = Depends(user), aud: str = Depends(viewer), limit: int = Query(30, ge=1, le=200)):
    rows = s.scalars(select(Question).where(Question.asker == u["user"], Question.audience == aud).order_by(Question.id.desc()).limit(limit))
    return [{"id": q.id, "text": q.text, "outcome": q.outcome, "asked_at": iso(q.asked_at)} for q in rows]


@router.get("/documents", summary="Documents the viewer may see")
def documents(s: Session = Depends(db), aud: str = Depends(viewer), q: str = "", tag: str = "", limit: int = Query(500, ge=1, le=5000)):
    stmt = select(Document).where(Document.tag.in_(allowed_tags(aud))).order_by(Document.external_id).limit(limit)
    if tag:
        stmt = stmt.where(Document.tag == tag)
    rows = [d for d in s.scalars(stmt) if not q or q.lower() in d.title.lower() or q.lower() in d.external_id.lower()]
    return [doc_dict(d) for d in rows]


@router.get("/documents/{doc_id}", summary="One document with its full text, for the source viewer")
def document(doc_id: int, s: Session = Depends(db), aud: str = Depends(viewer)):
    d = s.get(Document, doc_id)
    if d is None or d.tag not in allowed_tags(aud):
        raise HTTPException(404, "No such document.")
    return doc_dict(d, full=True)


@router.get("/sources", summary="Sources whose tag the viewer may see, with index status")
def sources(s: Session = Depends(db), aud: str = Depends(viewer)):
    tags = allowed_tags(aud)
    out = []
    for src in s.scalars(select(Source).order_by(Source.id)):
        per = dict(s.execute(select(Document.tag, func.count()).where(Document.source_id == src.id, Document.tag.in_(tags)).group_by(Document.tag)).all())
        if src.default_tag not in tags and not per:
            continue
        out.append({"id": src.id, "kind": src.kind, "name": src.name, "uri": src.uri, "default_tag": src.default_tag, "reliability": src.reliability, "owner": src.owner, "status": src.status,
                    "last_synced_at": iso(src.last_synced_at), "error": src.error, "documents": sum(per.values()), "by_tag": per,
                    "untagged_tag": untagged.get(s, src.id) or narrowest_tag()})
    return out


@router.get("/tasks", summary="Tasks the viewer may see")
def tasks(s: Session = Depends(db), aud: str = Depends(viewer), status: str = "", owner_id: int | None = None, limit: int = Query(2000, ge=1, le=10000)):
    stmt = select(Task).where(Task.tag.in_(allowed_tags(aud))).order_by(Task.due_on.is_(None), Task.due_on, Task.id).limit(limit)
    if status:
        stmt = stmt.where(Task.status.in_(status.split(",")))
    if owner_id is not None:
        stmt = stmt.where(Task.owner_id == owner_id)
    names = _names(s)
    return [task_dict(t, names) for t in s.scalars(stmt)]


@router.get("/tasks/{task_id}", summary="One task with its history")
def task(task_id: int, s: Session = Depends(db), aud: str = Depends(viewer)):
    t = s.get(Task, task_id)
    if t is None or t.tag not in allowed_tags(aud):
        raise HTTPException(404, "No such task.")
    out = task_dict(t, _names(s))
    out["events"] = [{"id": e.id, "kind": e.kind, "note": e.note, "actor": e.actor, "at": iso(e.at)} for e in t.events]
    out["meeting_title"] = t.meeting.title if t.meeting else ""
    return out


@router.get("/owners", summary="People who can own work")
def owners(s: Session = Depends(db), _: dict = Depends(user)):
    return [{"id": o.id, "name": o.name, "role": o.role} for o in s.scalars(select(Owner).order_by(Owner.name))]


@router.get("/stuck", summary="Stuck work with the evidence for each item")
def stuck_work(s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), aud: str = Depends(viewer)):
    return [{"kind": x.kind, "task_id": x.task_id, "owner": x.owner, "days": x.days, "evidence": x.evidence, "task_ids": x.task_ids} for x in stuck.detect(s, ctx.today(s), ctx.settings, allowed_tags(aud))]


@router.get("/meetings", summary="Meetings the viewer may see")
def meetings(s: Session = Depends(db), aud: str = Depends(viewer)):
    out = []
    for m in s.scalars(select(Meeting).where(Meeting.tag.in_(allowed_tags(aud))).order_by(Meeting.held_on.desc(), Meeting.id.desc())):
        n = s.scalar(select(func.count()).select_from(Task).where(Task.meeting_id == m.id)) or 0
        pend = s.scalar(select(func.count()).select_from(Task).where(Task.meeting_id == m.id, Task.status == "proposed")) or 0
        out.append({"id": m.id, "title": m.title, "held_on": iso(m.held_on), "provider": m.provider, "tag": m.tag, "attendees": m.attendees, "tasks": n, "proposed": pend, "flagged": len(m.flagged_lines or []), "extracted": m.extracted})
    return out


@router.get("/meetings/{mid}", summary="A meeting with its transcript, the action items found in it and lines that were not acted on")
def meeting(mid: int, s: Session = Depends(db), aud: str = Depends(viewer)):
    m = s.get(Meeting, mid)
    if m is None or m.tag not in allowed_tags(aud):
        raise HTTPException(404, "No such meeting.")
    names = _names(s)
    return {"id": m.id, "title": m.title, "held_on": iso(m.held_on), "provider": m.provider, "tag": m.tag, "attendees": m.attendees, "document_id": m.document_id, "transcript": m.transcript.text if m.transcript else "",
            "flagged_lines": m.flagged_lines or [], "tasks": [task_dict(t, names) for t in s.scalars(select(Task).where(Task.meeting_id == m.id).order_by(Task.quote_start))],
            "decisions": [decision_dict(d) for d in s.scalars(select(Decision).where(Decision.meeting_id == m.id).order_by(Decision.quote_start))]}


@router.get("/decisions", summary="The decision log")
def decisions(s: Session = Depends(db), aud: str = Depends(viewer), status: str = ""):
    stmt = select(Decision).where(Decision.tag.in_(allowed_tags(aud))).order_by(Decision.decided_on.desc(), Decision.id.desc())
    if status:
        stmt = stmt.where(Decision.status.in_(status.split(",")))
    rows = list(s.scalars(stmt))
    titles = {m.id: m.title for m in s.scalars(select(Meeting).where(Meeting.id.in_([d.meeting_id for d in rows if d.meeting_id] or [0])))}
    return [{**decision_dict(d), "meeting_title": titles.get(d.meeting_id, "")} for d in rows]


@router.get("/sops", summary="The SOP coverage map")
def sop_map(s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), aud: str = Depends(viewer)):
    procs = sops.visible(s, aud)
    tags = allowed_tags(aud)
    sop_docs = [d for d in s.scalars(select(Document).where(Document.doc_type == "sop", Document.tag.in_(tags)))]
    used = {p["sop"]["id"] for p in procs if p["sop"]}
    return {"processes": procs, "unmatched_sops": [{"id": d.id, "title": d.title, "owner": d.owner, "review_by": iso(d.review_by)} for d in sop_docs if d.id not in used]}


@router.get("/reviews", summary="Weekly operating reviews the viewer may read")
def reviews(s: Session = Depends(db), aud: str = Depends(viewer)):
    return [{"id": r.id, "week_start": iso(r.week_start), "scope": r.scope_tag, "title": r.title, "claims": r.claims, "linked": r.linked, "generated_at": iso(r.generated_at)} for r in review.visible_reviews(s, aud)]


@router.get("/reviews/{rid}", summary="One review as a document")
def review_one(rid: int, s: Session = Depends(db), aud: str = Depends(viewer)):
    r = next((x for x in review.visible_reviews(s, aud) if x.id == rid), None)
    if r is None:
        raise HTTPException(404, "No such review.")
    return {"id": r.id, "week_start": iso(r.week_start), "scope": r.scope_tag, "title": r.title, "body": r.body, "sections": r.sections, "claims": r.claims, "linked": r.linked, "generated_at": iso(r.generated_at)}


@router.get("/reminders", summary="Drafted and sent task reminders")
def reminders(s: Session = Depends(db), aud: str = Depends(viewer)):
    tags = allowed_tags(aud)
    names = _names(s)
    out = []
    for r in s.scalars(select(Reminder).order_by(Reminder.id.desc()).limit(200)):
        t = s.get(Task, r.task_id)
        if t and t.tag in tags:
            out.append({"id": r.id, "task_id": t.id, "task": t.title, "owner": names.get(t.owner_id, ""), "kind": r.kind, "on_date": iso(r.on_date), "body": r.body, "status": r.status})
    return out


@router.get("/company-folder", summary="Check results and tree of the company folder template in use (owner and leadership)")
def company_folder(ctx: Ctx = Depends(get_ctx), aud: str = Depends(real_audience), viewer_aud: str = Depends(viewer), s: Session = Depends(db)):
    if aud not in {"owner", "leadership"}:
        raise HTTPException(403, "Only the owner and leadership can see the folder check.")
    from pathlib import Path

    src = s.scalar(select(Source).where(Source.kind == "folder").order_by(Source.id))
    try:
        root = Path(ctx.settings.knowledge_dir) if ctx.settings.knowledge_dir else world.seed_dir(ctx) / "company"
    except FileNotFoundError:
        root = None
    if root is None or not root.exists():
        raise HTTPException(404, "The company folder is not on this machine. Set KNOWLEDGE_DIR.")
    rep = folder_tool.check(root, ctx.today(s))
    tags = allowed_tags(viewer_aud)
    # The tag shown for a path is the tag stored for the indexed document, not the line in the file: after a retag or a folder tag the file alone would say something else.
    stored = {d.external_id: d.tag for d in s.scalars(select(Document).where(Document.source_id == src.id))} if src is not None else {}
    tag_of = {p.relative_to(root.resolve()).as_posix(): stored.get(p.relative_to(root.resolve()).as_posix()) or narrowest_tag() for p in folder_tool.iter_docs(root.resolve())}
    show = lambda path: path not in tag_of or tag_of[path] in tags  # noqa: E731  (a folder or the index is not a document)
    rep.findings = [f for f in rep.findings if show(f.path)]
    rep.tree = [{**t, "documents": [{**d, "visibility": tag_of.get(d["path"], narrowest_tag())} for d in t["documents"] if show(d["path"])]} for t in rep.tree]
    return {"name": src.name if src else root.name, "documents": len(tag_of), "documents_visible": sum(1 for p in tag_of if show(p)), "ok": rep.ok, "errors": sum(f.severity == "error" for f in rep.findings), "warnings": sum(f.severity == "warning" for f in rep.findings),
            "findings": [f.__dict__ for f in rep.findings], "tree": rep.tree}


@router.get("/audiences", summary="Which tags each audience may see (for the Sources page and for previews)")
def audiences(_: dict = Depends(user)):
    return {k: list(v) for k, v in AUDIENCE_TAGS.items()}
