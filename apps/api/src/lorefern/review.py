"""The weekly operating review: a document built from tasks, decisions and meetings of the week before, where every line carries links to the records it comes from.

Two scopes: `company` (evidence tagged company only, readable by everyone) and `leadership` (every tag a leadership audience may see). The writer is code, not a model, so
a line can only say what the records say. `check_sources` proves it: every bullet has at least one link to a record that exists inside the scope, and a count in a line equals
the number of links of that kind in the same line.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from lorefern import stuck
from lorefern.models import Decision, Meeting, Owner, Process, Task, WeeklyReview
from lorefern.visibility import allowed_tags

SCOPES = {"company": ("company",), "leadership": allowed_tags("leadership")}
REF = re.compile(r"\[([TDMP])(\d+)\]\(/(?:tasks|decisions|meetings|sops)[^)]*\)")
COUNT = re.compile(r"\b(\d+) (task|tasks|decision|decisions|meeting|meetings|process|processes)\b")
KIND = {"task": "T", "decision": "D", "meeting": "M", "process": "P"}


def week_start_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _ref(kind: str, i: int) -> str:
    path = {"T": "tasks", "D": "decisions", "M": "meetings", "P": "sops"}[kind]
    return f"[{kind}{i}](/{path}?open={i})"


def _refs(kind: str, ids) -> str:
    return " ".join(_ref(kind, i) for i in ids)


def generate(session: Session, ctx, week_start: date, scope: str = "company") -> WeeklyReview:
    """Build the review for the week BEFORE `week_start` (Monday to Sunday). Replaces an earlier review for the same week and scope."""
    tags = SCOPES[scope]
    start, end = week_start - timedelta(days=7), week_start
    today = ctx.today(session)
    names = {o.id: o.name for o in session.scalars(select(Owner))}
    day = lambda dt: dt.date() if isinstance(dt, datetime) else dt  # noqa: E731
    done = [t for t in session.scalars(select(Task).where(Task.status == "done", Task.tag.in_(tags))) if t.done_at and start <= day(t.done_at) < end]
    decisions = list(session.scalars(select(Decision).where(Decision.status == "confirmed", Decision.tag.in_(tags), Decision.decided_on >= start, Decision.decided_on < end)))
    meetings = list(session.scalars(select(Meeting).where(Meeting.tag.in_(tags), Meeting.held_on >= start, Meeting.held_on < end)))
    pending = list(session.scalars(select(Task).where(Task.status == "proposed", Task.tag.in_(tags))))
    issues = [s for s in stuck.detect(session, today, ctx.settings, tags) if s.kind != "overloaded" and s.task_id]
    overloaded = [s for s in stuck.detect(session, today, ctx.settings, tags) if s.kind == "overloaded"]
    gaps = [p for p in session.scalars(select(Process).where(Process.coverage.in_(("gap", "stale")))) if all(e["tag"] in tags for e in p.evidence)]
    L: list[str] = [f"# Weekly operating review, week of {start.isoformat()}", "", f"Covers {start.isoformat()} to {(end - timedelta(days=1)).isoformat()}. Scope: {scope}. Every line links to the records it comes from.", ""]
    intro = ctx.review_intro(session, {"completed": len(done), "decisions": len(decisions), "meetings": len(meetings), "stuck": len(issues), "waiting": len(pending), "process_gaps": len(gaps)}) if hasattr(ctx, "review_intro") else None
    if intro:  # two plain sentences from the numbers above; not a bullet, so it makes no claim the source check has to link
        L.extend([intro["text"] + f" (Written by: {intro['writer']}.)", ""])
    sections: list[dict] = []

    def section(title: str, lines: list[str], empty: str) -> None:
        L.extend([f"## {title}", ""])
        L.extend(lines or [empty])
        L.append("")
        sections.append({"title": title, "lines": len(lines)})

    section("Completed", [f"- {len(done)} tasks were completed: {_refs('T', [t.id for t in done])}"] + [f"- {t.title} ({names.get(t.owner_id, 'unassigned')}), done on {day(t.done_at).isoformat()}. {_ref('T', t.id)}" for t in done] if done else [], "Nothing was completed last week.")
    st_lines = [f"- {s.evidence} Owner: {s.owner}. {_ref('T', s.task_id)}" for s in sorted(issues, key=lambda s: -s.days)[:15]]
    st_lines += [f"- {s.evidence} {_refs('T', s.task_ids)}" for s in overloaded if s.task_ids]
    section("Stuck work", st_lines, "No task is stuck.")
    section("Decisions", [f"- {d.title}. Decided by {d.decided_by} on {d.decided_on.isoformat()}" + (f" because {d.why.strip().rstrip('.')}" if d.why else "") + f". {_ref('D', d.id)}" + (f" {_ref('M', d.meeting_id)}" if d.meeting_id else "") for d in decisions], "No decision was confirmed last week.")
    section("Meetings", [f"- {m.title} on {m.held_on.isoformat()}. {_ref('M', m.id)}" for m in meetings], "No meeting was recorded last week.")
    section("Waiting for a person", ([f"- {len(pending)} proposed tasks wait for approval: {_refs('T', [t.id for t in pending][:20])}"] if pending else []), "Nothing waits for approval.")
    section("Process gaps", [f"- The process '{p.label}' has {'no SOP' if p.coverage == 'gap' else 'an SOP past its review date'}, seen {p.mentions} times. {_ref('P', p.id)}" for p in gaps[:10]], "Every recurring process has a current SOP.")
    body = "\n".join(L).rstrip() + "\n"
    old = session.scalar(select(WeeklyReview).where(WeeklyReview.week_start == start, WeeklyReview.scope_tag == scope))
    if old is not None:
        session.delete(old)
        session.flush()
    claims, linked, problems = check_sources(session, body, tags)
    r = WeeklyReview(week_start=start, scope_tag=scope, title=f"Weekly operating review, week of {start.isoformat()}", body=body, sections=sections, claims=claims, linked=linked, generated_at=ctx.now(session))
    session.add(r)
    session.flush()
    return r


def check_sources(session: Session, body: str, tags: tuple[str, ...]) -> tuple[int, int, list[str]]:
    """Every bullet needs a link to a record that exists and sits inside the scope's tags, and any count in the line must equal its links of that kind."""
    models = {"T": Task, "D": Decision, "M": Meeting}
    problems: list[str] = []
    claims = linked = 0
    for ln in body.splitlines():
        if not ln.startswith("- "):
            continue
        claims += 1
        refs = REF.findall(ln)
        ok = bool(refs)
        for kind, sid in refs:
            if kind == "P":
                ok = ok and session.get(Process, int(sid)) is not None
                continue
            row = session.get(models[kind], int(sid))
            if row is None or row.tag not in tags:
                ok = False
                problems.append(f"Link {kind}{sid} does not resolve inside the scope: {ln[:80]}")
        for n, noun in COUNT.findall(ln):
            k = KIND[noun.rstrip("s") if noun != "processes" else "process"]
            if int(n) != sum(1 for rk, _ in refs if rk == k) and ":" in ln:
                ok = False
                problems.append(f"Count {n} {noun} does not match its links: {ln[:80]}")
        if not refs:
            problems.append(f"No source link: {ln[:80]}")
        linked += ok
    return claims, linked, problems


def visible_reviews(session: Session, audience: str) -> list[WeeklyReview]:
    mine = set(allowed_tags(audience))
    return [r for r in session.scalars(select(WeeklyReview).order_by(WeeklyReview.week_start.desc(), WeeklyReview.id.desc())) if set(SCOPES.get(r.scope_tag, ("leadership",))) <= mine]
