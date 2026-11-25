"""The live event stream, per person. The shared base caps the whole process at 50 streams and has no way to end a session, so one signed in person could use every stream up, and a
stream outlived a sign out or the end of the session. This guard (in this app, in front of the base route) gives each person a small number of streams, closes a stream within about
a second of the session ending, and remembers signed out tokens (in memory, until they would have expired anyway) so a signed out token stops working at once on this server."""

from __future__ import annotations

import base64
import hashlib
import json
import time
from collections.abc import AsyncIterator

from sendora_core.auth import read_session_token

MAX_PER_PERSON = 5  # live streams one person may hold at once (a few tabs). The base caps the whole process at 50.
MAX_ENDED = 10_000  # signed out tokens remembered at once


def _fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _expiry(token: str) -> float:
    try:
        body = token.split(".", 1)[0]
        return float(json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))["exp"])
    except (ValueError, KeyError, TypeError, IndexError):
        return 0.0


class StreamGuard:
    def __init__(self, per_person: int = MAX_PER_PERSON):
        self.per_person = per_person
        self.open: dict[str, int] = {}
        self.ended: dict[str, float] = {}  # token fingerprint: when the token would have expired

    def admit(self, user: str) -> bool:
        return self.open.get(user, 0) < self.per_person

    def end(self, token: str) -> None:
        """A person signed out: the token is dead on this server, and its streams close at their next beat."""
        now = time.time()
        for k in [k for k, exp in self.ended.items() if exp < now]:
            del self.ended[k]
        if len(self.ended) < MAX_ENDED:
            self.ended[_fingerprint(token)] = _expiry(token)

    def is_ended(self, token: str) -> bool:
        return _fingerprint(token) in self.ended

    async def wrap(self, user: str, token: str, secret: str, frames: AsyncIterator) -> AsyncIterator:
        """Pass the frames through while the session is alive. Every frame (an idle stream sends a heartbeat each second) checks that the token has not expired or been signed out."""
        self.open[user] = self.open.get(user, 0) + 1
        try:
            async for frame in frames:
                if self.is_ended(token) or read_session_token(secret, token) is None:
                    return
                yield frame
        finally:
            self.open[user] = max(0, self.open.get(user, 1) - 1)
            if not self.open[user]:
                del self.open[user]
            close = getattr(frames, "aclose", None)
            if close is not None:
                await close()
