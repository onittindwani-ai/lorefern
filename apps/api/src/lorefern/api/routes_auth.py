from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from lorefern import visibility
from lorefern.api.deps import get_ctx, user
from lorefern.context import Ctx
from sendora_core.app import SESSION_COOKIE
from sendora_core.auth import clean_email, make_session_token, read_session_token, verify_password_or_dummy
from sendora_core.ratelimit import RateLimitExceeded

router = APIRouter(prefix="/api/auth", tags=["auth"])
SESSION_TTL_S = 8 * 3600  # the shared base default: how long a session token lasts
DEMO_PASSWORD = "demo-password-1"  # only accepted when settings.demo_shortcuts is true: DEMO_MODE on AND no OWNER_PASSWORD_HASH set


class Login(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=1024)


def _accounts(ctx: Ctx) -> dict[str, tuple[str | None, str]]:
    """email to (password hash, audience). The owner, the approver and anyone in MEMBERS_JSON with a password_hash can sign in for real. The sample demo accounts, and the owner without
    a password, exist only while the public demo password is on (settings.demo_shortcuts), never next to a real owner password."""
    s = ctx.settings
    out: dict[str, tuple[str | None, str]] = {}
    for email, audience in s.members().items():
        email = clean_email(email)
        h = s.owner_password_hash if email == clean_email(s.owner_email) else (s.approver_password_hash if s.approver_email and email == clean_email(s.approver_email) else s.member_hashes().get(email))
        if h is not None or s.demo_shortcuts:
            out[email] = (h, audience)
    return out


@router.post("/login", summary="Sign in with email and password")
def login(body: Login, request: Request, ctx: Ctx = Depends(get_ctx)):
    email = clean_email(body.email)  # one spelling, used for the throttle key AND the lookup
    host = request.client.host if request.client else "x"
    try:
        request.app.state.login_ip_bucket.check(host)  # every try from one address, whatever email it names
        request.app.state.login_bucket.check(f"{host}:{email}")  # tries at one account from one address
        request.app.state.login_account_bucket.check(email)  # tries at one account from anywhere
    except RateLimitExceeded as exc:
        raise HTTPException(429, str(exc)) from exc
    acc = _accounts(ctx).get(email)
    pw_hash = acc[0] if acc else None
    if acc and pw_hash is None and ctx.settings.demo_shortcuts:
        ok = hmac.compare_digest(body.password.encode(), DEMO_PASSWORD.encode())
    else:
        ok = verify_password_or_dummy(body.password, pw_hash)  # an unknown account costs the same time as a wrong password
    if not acc or not ok:
        raise HTTPException(401, "Email or password is wrong.")
    # The session role follows the audience: the owner is `owner`, leadership is `approver`, and the read only audiences (finance, staff) are the base `viewer` role.
    # What a person may see is still decided from the audience (visibility.py); the base role is a second lock on changes.
    role = visibility.session_role(acc[1])
    token, ttl = make_session_token(ctx.settings.session_secret, email, role), SESSION_TTL_S
    while request.app.state.streams.is_ended(token) and ttl > SESSION_TTL_S - 120:  # the same person signing in again in the second after signing out would be given the very token that was just ended
        ttl -= 1
        token = make_session_token(ctx.settings.session_secret, email, role, ttl_s=ttl)
    return {"token": token, "user": email, "role": acc[1]}


@router.post("/logout", summary="End the session: the token stops working on this server and its live streams close (the web app also clears the cookie)")
def logout(request: Request, ctx: Ctx = Depends(get_ctx)):
    token = request.cookies.get(SESSION_COOKIE) or request.headers.get("x-session")
    if token and read_session_token(ctx.settings.session_secret, token) is not None:  # only a real token is remembered, so nobody can fill the list with junk
        request.app.state.streams.end(token)
    return {"ok": True}


@router.get("/me", summary="Who is signed in")
def me(u: dict = Depends(user), ctx: Ctx = Depends(get_ctx)):
    aud = visibility.audience_of(ctx.settings, u["user"])
    return {"user": u["user"], "role": aud, "audience": aud, "can_write": visibility.can_write(aud), "demo_mode": ctx.settings.demo_shortcuts}  # the demo bar shows only while those routes exist
