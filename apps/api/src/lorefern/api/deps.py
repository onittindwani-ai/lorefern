from __future__ import annotations

from collections.abc import Iterator

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from lorefern import visibility
from lorefern.context import Ctx
from sendora_core.auth import WRITE_ROLES


KILL_MESSAGE = "The kill switch is on, so nothing is changed. The owner can turn it off from the banner."


def get_ctx(request: Request) -> Ctx:
    return request.app.state.ctx


def db(request: Request) -> Iterator[Session]:
    s = request.app.state.ctx.factory()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def user(request: Request) -> dict:
    u = getattr(request.state, "user", None)
    if not u:
        raise HTTPException(401, "Sign in to continue.")
    return u


def real_audience(request: Request) -> str:
    return visibility.audience_of(request.app.state.ctx.settings, user(request)["user"])


def viewer(request: Request) -> str:
    """The audience whose tags filter every read. An owner may preview a narrower audience with ?as=staff. Nobody can preview a wider one."""
    real = real_audience(request)
    wanted = request.query_params.get("as", "")
    if real == "owner" and wanted in visibility.AUDIENCES:
        return wanted
    return real


def kill_switch_on(request: Request) -> bool:
    ctx = request.app.state.ctx
    with ctx.factory() as s:
        return ctx.effective(s).kill_switch


def writer(request: Request) -> dict:
    """Changes need an owner or leadership audience, never while previewing, never through a read only audience, and never while the kill switch is on."""
    u = user(request)
    if u["role"] not in WRITE_ROLES or not visibility.can_write(real_audience(request)) or request.query_params.get("as"):
        raise HTTPException(403, "Your audience can read but not change things.")
    if kill_switch_on(request):
        raise HTTPException(409, KILL_MESSAGE)
    return {**u, "audience": real_audience(request)}


def owner(request: Request) -> dict:
    u = user(request)
    if real_audience(request) != "owner" or request.query_params.get("as"):
        raise HTTPException(403, "Only the owner can do this.")
    return {**u, "audience": "owner"}


def owner_write(request: Request) -> dict:
    """An owner only change to data. Turning the kill switch off and resetting the demo use `owner`, because they must work while it is on."""
    u = owner(request)
    if kill_switch_on(request):
        raise HTTPException(409, KILL_MESSAGE)
    return u


def demo_only(request: Request) -> None:
    if not request.app.state.ctx.settings.demo_mode:
        raise HTTPException(404, "Not found.")


def leaders(request: Request) -> str:
    """Pages about changes and approvals are for the owner and leadership only (previewing does not matter, nothing is changed by reading)."""
    aud = real_audience(request)
    if aud not in {"owner", "leadership"}:
        raise HTTPException(403, "Only the owner and leadership can see this page.")
    return aud
