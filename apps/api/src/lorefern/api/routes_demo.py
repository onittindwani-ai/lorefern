"""Demo mode only. These routes return 404 when DEMO_MODE is off."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from lorefern import clock, demo
from lorefern.api.deps import db, demo_only, get_ctx, owner, writer
from lorefern.context import Ctx
from lorefern.jobs import run_cycle

router = APIRouter(prefix="/api/demo", tags=["demo"], dependencies=[Depends(demo_only)])


@router.get("/state", summary="The demo clock")
def state(s: Session = Depends(db), ctx: Ctx = Depends(get_ctx)):
    return {"now": ctx.now(s).isoformat()}


@router.post("/reset", summary="Reset to the seed data and a fresh clock")
def reset(s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(owner)):
    if demo.real_sources(s):
        raise HTTPException(409, "This database holds a source that is not part of the demo, so it is not erased.")
    try:
        return demo.reset(s, ctx)
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/tick", summary="Run every job once, now")
def tick(s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    return run_cycle(s, ctx)


class AdvanceIn(BaseModel):
    hours: float = Field(ge=0, le=24 * 30)


@router.post("/advance", summary="Move the demo clock forward")
def advance(b: AdvanceIn, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    return {"now": clock.advance(s, b.hours).isoformat()}


class StressIn(BaseModel):
    n: int = Field(ge=1, le=20000)


@router.post("/stress-tasks", summary="Add many fictional tasks, to check that long tables stay fast")
def stress(b: StressIn, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(owner)):
    from lorefern.models import Task

    now = ctx.now(s)
    s.bulk_insert_mappings(Task, [{"title": f"Fictional load task {i}", "owner_raw": "", "due_on": None, "due_raw": "", "status": "done", "confidence": 1.0, "quote": "", "quote_start": -1, "tag": "company", "process_key": "",
                                   "blocked_reason": "", "created_at": now - timedelta(minutes=i), "updated_at": now - timedelta(minutes=i), "done_at": now - timedelta(minutes=i)} for i in range(b.n)])
    return {"added": b.n}
