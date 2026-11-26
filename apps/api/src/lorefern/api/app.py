"""The Lorefern API. Every route under /api needs a signed in session, except sign in and the signed webhooks."""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from lorefern.api import routes_admin, routes_auth, routes_demo, routes_read, routes_write
from lorefern.api.streams import StreamGuard
from lorefern.config import Settings
from lorefern.context import Ctx
from lorefern.world import REPO_DATA
from sendora_core.app import SESSION_COOKIE, create_base_app
from sendora_core.auth import read_session_token
from sendora_core.db import Base, make_engine, make_session_factory
from sendora_core.ratelimit import TokenBucket

PUBLIC = {"/api/auth/login", "/api/auth/logout"}
PUBLIC_PREFIX = ()


def _seed_if_empty(ctx: Ctx) -> None:
    from sqlalchemy import select

    from lorefern import demo
    from lorefern.models import Owner

    with ctx.factory() as s:
        if s.scalars(select(Owner).limit(1)).first() is None:
            try:
                demo.reset(s, ctx)
            except FileNotFoundError as exc:  # no demo data folder (an installed copy without SEED_DIR): start empty, and say why
                logging.getLogger("lorefern").warning("%s", exc)


def create_app(settings: Settings | None = None, ctx: Ctx | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.check_runtime()  # an unsafe configuration stops here, before the database is opened or any table is made
    if ctx is None:
        engine = make_engine(settings.database_url)
        from sendora_core import models as _c  # noqa: F401
        import lorefern.models  # noqa: F401

        if settings.database_url.startswith("sqlite"):
            Base.metadata.create_all(engine)  # SQLite zero setup path. Postgres uses `alembic upgrade head`.
        ctx = Ctx(settings, make_session_factory(engine))
        if not settings.seed_dir and REPO_DATA is not None and (REPO_DATA / "seed").is_dir():
            ctx.settings.seed_dir = str(REPO_DATA)  # a source checkout; an installed copy (the Docker image) is told with SEED_DIR
    app = create_base_app(ctx.settings, ctx.factory)  # refuses an unsafe configuration before anything is written
    if ctx.settings.demo_shortcuts:
        _seed_if_empty(ctx)
    app.title, app.version = "Lorefern API", "1.0.2"
    app.state.ctx = ctx
    app.state.limiter = TokenBucket(capacity=600, refill_per_sec=20.0)
    app.state.streams = StreamGuard()
    # Sign in attempts per address and email: a burst of LOGIN_BURST (default 5), then one more every 12 seconds.
    app.state.login_bucket = TokenBucket(capacity=ctx.settings.login_burst, refill_per_sec=1 / 12)
    # And a wider limit per address alone, so changing the email in every try does not give a fresh set of tries.
    app.state.login_ip_bucket = TokenBucket(capacity=max(30, ctx.settings.login_burst * 6), refill_per_sec=1 / 3)
    # And one per account whatever the address, so guesses spread over many addresses still run out. Generous, and it refills every 30 seconds, so the owner is
    # held up for a short while at most by someone hammering the account, never locked out.
    app.state.login_account_bucket = TokenBucket(capacity=max(20, ctx.settings.login_burst * 4), refill_per_sec=1 / 30)

    @app.middleware("http")
    async def require_session(request: Request, call_next):
        p = request.url.path
        if p.startswith("/api/") and p not in PUBLIC and not p.startswith(PUBLIC_PREFIX):
            token = request.cookies.get(SESSION_COOKIE) or request.headers.get("x-session")
            data = read_session_token(ctx.settings.session_secret, token) if token else None
            if data is None or app.state.streams.is_ended(token):  # a token that was signed out stops working here at once
                return JSONResponse({"error": {"code": "http_401", "message": "Sign in to continue."}}, 401)
            request.state.user = data
            if p == "/api/events/stream":  # the shared base serves it; this keeps one person from using every stream, and ends a stream with its session
                if not app.state.streams.admit(data["user"]):
                    return JSONResponse({"error": {"code": "http_429", "message": "You already have several live streams open. Close another tab and try again."}}, 429)
                response = await call_next(request)
                if response.status_code == 200:
                    response.body_iterator = app.state.streams.wrap(data["user"], token, ctx.settings.session_secret, response.body_iterator)
                return response
        return await call_next(request)

    for r in (routes_auth, routes_read, routes_write, routes_admin, routes_demo):
        app.include_router(r.router)
    return app


def app_from_env() -> FastAPI:  # uvicorn lorefern.api.app:app_from_env --factory
    return create_app(Settings(_env_file=os.environ.get("ENV_FILE", ".env")))
