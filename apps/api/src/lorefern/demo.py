"""Demo mode: reset to the seed data and move the clock. Fictional people, offline stand ins, nothing real is touched."""

from __future__ import annotations

from sqlalchemy.orm import Session

from lorefern import clock, review, search, sops, world
from sendora_core.db import Base


def reset(session: Session, ctx, process: bool = True) -> dict:
    """Erase every table and load the demo data. It exists only for a demo with no owner password: with a real owner it refuses, whatever route called it."""
    if not ctx.settings.demo_shortcuts:
        raise PermissionError("The demo reset is only available in demo mode with no owner password set.")
    world.check_seed(ctx)  # read the data folder BEFORE anything is erased: a missing folder must not leave an empty database
    engine = session.get_bind()
    session.rollback()
    session.close()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with ctx.factory() as s:
        clock.set_offset(s, 0.0)
        s.flush()
        info = world.load_world(s, ctx)
        search.rebuild(s)
        out = {}
        if process:
            out = world.process_new(s, ctx)
            sops.detect(s, ctx.today(s), ctx.settings, wording=ctx.wording(s))
            ws = review.week_start_of(ctx.today(s))
            for scope in review.SCOPES:
                review.generate(s, ctx, ws, scope)
        s.commit()
        return {"seed": info, "processed": out}


DEMO_SOURCES = {("folder", "company"), ("slack", "slack"), ("meetings", "meetings")}


def real_sources(session: Session) -> list[str]:
    """Names of sources that are not the three the demo creates. A demo reset erases every table, so it refuses when someone has connected something of their own."""
    from sqlalchemy import select

    from lorefern.models import Source

    return [x.name for x in session.scalars(select(Source)) if (x.kind, x.uri) not in DEMO_SOURCES]
