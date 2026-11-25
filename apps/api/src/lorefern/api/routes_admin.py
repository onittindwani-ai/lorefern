from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from lorefern import reminders as rem
from lorefern.api.deps import db, get_ctx, leaders, owner, real_audience, writer
from lorefern.api.serializers import iso
from lorefern.context import Ctx, set_state
from lorefern.models import Decision, Document, Meeting, Reminder, Task
from lorefern.registry import CATEGORIES, ENV_VARS, missing_settings
from lorefern.visibility import allowed_tags
from sendora_core.approvals import ApprovalError, decide
from sendora_core.audit import record_audit, verify_audit_chain
from sendora_core.models import Approval, AuditEntry

router = APIRouter(prefix="/api", tags=["admin"])


@router.get("/approvals", summary="Pending and recent approvals")
def approvals(s: Session = Depends(db), _: str = Depends(leaders)):
    rows = list(s.scalars(select(Approval).order_by(Approval.id.desc()).limit(100)))
    return [{"id": a.id, "action": a.action, "summary": a.summary, "risk": a.risk, "status": a.status, "requested_by": a.requested_by, "decided_by": a.decided_by, "note": a.decision_note, "created_at": iso(a.created_at), "payload": a.payload} for a in rows]


class DecideIn(BaseModel):
    approve: bool
    note: str = Field(default="", max_length=500)


@router.post("/approvals/{approval_id}/decide", summary="Approve or reject")
def decide_approval(approval_id: int, body: DecideIn, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    try:
        a = decide(s, approval_id, body.approve, u["user"], u["role"], body.note or None)
    except ApprovalError as exc:
        raise HTTPException(409, str(exc)) from exc
    if a.action == "reminders.send" and body.approve:
        ids = [int(x) for x in a.payload.get("ids", [])]
        sent = rem.send(s, ctx.effective(s), ctx.adapters.email, ids)
        record_audit(s, u["user"], "reminders.sent", f"approval:{a.id}", {"sent": sent})
    return {"status": a.status}


_HIDDEN_KINDS = {"task": Task, "meeting": Meeting, "decision": Decision, "document": Document}


def _row_of(target: str | None) -> tuple[str, int] | None:
    kind, _, rid = (target or "").partition(":")
    return (kind, int(rid)) if kind in _HIDDEN_KINDS and rid.isdigit() else None


def _visible_entries(s: Session, entries: list, audience: str) -> list:
    """Drop entries about a task, meeting, decision or document this person may not see: the log must not tell leadership that a people row exists, or what was typed on it."""
    tags = allowed_tags(audience)
    wanted: dict[str, set[int]] = {}
    for e in entries:
        row = _row_of(e.target)
        if row:
            wanted.setdefault(row[0], set()).add(row[1])
    hidden: set[tuple[str, int]] = set()
    for kind, ids in wanted.items():
        model = _HIDDEN_KINDS[kind]
        seen = set(s.scalars(select(model.id).where(model.id.in_(ids), model.tag.in_(tags))))
        hidden |= {(kind, i) for i in ids if i not in seen}
    return [e for e in entries if _row_of(e.target) not in hidden]


@router.get("/audit", summary="Audit log, newest first")
def audit(limit: int = Query(100, ge=1, le=1000), s: Session = Depends(db), aud: str = Depends(leaders)):
    rows = _visible_entries(s, list(s.scalars(select(AuditEntry).order_by(AuditEntry.id.desc()).limit(limit))), aud)
    return [{"id": e.id, "actor": e.actor, "action": e.action, "target": e.target, "detail": e.detail, "at": e.created_at} for e in rows]


@router.get("/audit/verify", summary="Check the audit chain has not been edited")
def audit_verify(s: Session = Depends(db), _: str = Depends(leaders)):
    ok, bad = verify_audit_chain(s)
    return {"ok": ok, "first_bad_id": bad}


@router.get("/integrations", summary="Every adapter, which one is selected, and what it needs")
def integrations(ctx: Ctx = Depends(get_ctx), _: str = Depends(leaders)):
    st = ctx.settings
    chosen = {c: getattr(st, f"{c}_adapter") for c in CATEGORIES}
    out = []
    for row in ctx.registry.describe():
        env = ENV_VARS.get((row["category"], row["name"]), [])
        out.append({**row, "selected": chosen.get(row["category"]) == row["name"] or row["name"] in {"folder", "slack_export", "file"}, "env_vars": env, "configured": not missing_settings(st, row["category"], row["name"])})
    return {"categories": list(CATEGORIES), "adapters": out, "demo_mode": st.demo_shortcuts}


@router.post("/integrations/{category}/test", summary="Test the selected adapter in a category")
def test_integration(category: str, ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    if category not in CATEGORIES:
        raise HTTPException(404, "Unknown category.")
    ok, detail = getattr(ctx.adapters, category).healthcheck()
    return {"category": category, "ok": ok, "detail": detail}


@router.get("/settings", summary="Mode, kill switch and config problems")
def get_settings(s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), aud: str = Depends(real_audience)):
    eff = ctx.effective(s)
    st = ctx.settings
    full = {"mode": st.mode.value, "effective_mode": eff.mode.value, "kill_switch": eff.kill_switch, "demo_mode": st.demo_shortcuts, "problems": st.problems(), "company": st.company_name,
            "writer": "offline rules (not a language model)" if ctx.writer is None else "custom writer", "search": "SQLite full text plus a hashed word vector (not a language model embedding)",
            "rules": {"stuck_no_update_days": st.stuck_no_update_days, "stuck_blocked_days": st.stuck_blocked_days, "overload_open_tasks": st.overload_open_tasks, "working_days": st.working_days, "sop_review_days": st.sop_review_days}}
    if aud in {"owner", "leadership"}:
        return full
    return {**full, "mode": eff.mode.value, "problems": [], "rules": {}}  # everyone sees the banner facts (mode, kill switch); how the install is set up is for the owner and leadership


class SettingsIn(BaseModel):
    kill_switch: bool | None = None
    force_draft: bool | None = None


@router.post("/settings", summary="Turn the kill switch or draft mode on or off (owner only). The app can never switch live mode on.")
def post_settings(body: SettingsIn, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(owner)):
    if body.kill_switch is not None:
        set_state(s, "kill_switch", "1" if body.kill_switch else "0")
        record_audit(s, u["user"], "settings.kill_switch", None, {"on": body.kill_switch})
    if body.force_draft is not None:
        set_state(s, "force_draft", "1" if body.force_draft else "0")
        record_audit(s, u["user"], "settings.force_draft", None, {"on": body.force_draft})
    s.flush()
    return get_settings(s, ctx, "owner")
