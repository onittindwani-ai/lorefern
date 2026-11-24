"""Demo mode: reset to the seed data and move the clock. Fictional people, offline stand ins, nothing real is touched."""

from __future__ import annotations

from sqlalchemy.orm import Session

from lorefern import clock, review, search, sops, world
from sendora_core.db import Base


def reset(session: Session, ctx, process: bool = True) -> dict:
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
