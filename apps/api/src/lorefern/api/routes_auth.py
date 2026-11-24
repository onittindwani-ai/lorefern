from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from lorefern import visibility
from lorefern.api.deps import get_ctx, user
from lorefern.context import Ctx
from sendora_core.auth import hash_password, make_session_token, verify_password
from sendora_core.ratelimit import RateLimitExceeded, TokenBucket

router = APIRouter(prefix="/api/auth", tags=["auth"])
DEMO_PASSWORD = "demo-password-1"  # only accepted when DEMO_MODE is true and no password hash is set


class Login(BaseModel):
    email: str
    password: str


def _accounts(ctx: Ctx) -> dict[str, tuple[str | None, str]]:
    """email to (password hash, audience). The owner, the approver and anyone in MEMBERS_JSON with a password_hash can sign in for real. The extra demo accounts exist in demo mode only."""
    s = ctx.settings
    out: dict[str, tuple[str | None, str]] = {}
    for email, audience in s.members().items():
        h = s.owner_password_hash if email == s.owner_email.lower() else (s.approver_password_hash if s.approver_email and email == s.approver_email.lower() else s.member_hashes().get(email))
        if h is not None or s.demo_mode:
            out[email] = (h, audience)
    return out


@router.post("/login", summary="Sign in with email and password")
def login(body: Login, request: Request, ctx: Ctx = Depends(get_ctx)):
    key = f"{request.client.host if request.client else 'x'}:{body.email.lower()}"
    try:
        request.app.state.login_bucket.check(key)
    except RateLimitExceeded as exc:
        raise HTTPException(429, str(exc)) from exc
    acc = _accounts(ctx).get(body.email.strip().lower())
    ok = False
    if acc:
        h, _ = acc
        ok = verify_password(body.password, h) if h else (ctx.settings.demo_mode and body.password == DEMO_PASSWORD)
    if not acc or not ok:
        raise HTTPException(401, "Email or password is wrong.")
    # The session role follows the audience: the owner is `owner`, leadership is `approver`, and the read only audiences (finance, staff) are the base `viewer` role.
    # What a person may see is still decided from the audience (visibility.py); the base role is a second lock on changes.
    token = make_session_token(ctx.settings.session_secret, body.email.strip().lower(), visibility.session_role(acc[1]))
    return {"token": token, "user": body.email.strip().lower(), "role": acc[1]}


@router.post("/logout", summary="End the session (the web app clears the cookie)")
def logout():
    return {"ok": True}


@router.get("/me", summary="Who is signed in")
def me(u: dict = Depends(user), ctx: Ctx = Depends(get_ctx)):
    aud = visibility.audience_of(ctx.settings, u["user"])
    return {"user": u["user"], "role": aud, "audience": aud, "can_write": visibility.can_write(aud), "demo_mode": ctx.settings.demo_mode}
