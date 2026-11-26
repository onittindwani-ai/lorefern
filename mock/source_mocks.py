"""Mock Google token service, Google Drive and Notion servers (read only). Shapes from the public docs, UNVERIFIED live."""

from __future__ import annotations

import base64
import json
import re
from urllib.parse import parse_qs

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse, PlainTextResponse


class StubClock:
    """A clock the tests move by hand, shared by the token provider and the mock Google servers."""

    def __init__(self, start: float = 1_800_000_000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _b64d(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


class GoogleTokenMock:
    """A local imitation of the Google token address (POST /token), shapes from Google's public OAuth documents. NOT the real service.

    Accepts the service account JWT grant (checks the RS256 signature, issuer, audience, scope and a lifetime of at most an hour) and the refresh token grant.
    Issues access tokens that expire on the shared test clock. `mode` can be set to "invalid_grant", "invalid_client" or "server_error" to test failures.
    """

    def __init__(self, clock: StubClock | None = None, lifetime: int = 3600, audience: str = "http://testserver/token"):
        self.clock, self.lifetime, self.audience = clock or StubClock(), lifetime, audience
        self.service_accounts: dict[str, object] = {}  # client_email -> RSA public key
        self.refresh_tokens: dict[str, tuple[str, str]] = {}  # refresh token -> (client_id, client_secret)
        self.issued: dict[str, float] = {}  # access token -> expiry on the test clock
        self.requests: list[dict] = []  # grant type and outcome of every call, never a secret
        self.mode = ""
        self.app = FastAPI()

        @self.app.post("/token")
        async def token(request: Request):
            form = {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}
            grant = form.get("grant_type", "")
            self.requests.append({"grant": grant})
            if self.mode == "server_error":
                return JSONResponse({"error": "backend_error"}, 503)
            if self.mode in {"invalid_grant", "invalid_client"}:
                return JSONResponse({"error": self.mode, "error_description": "SECRET-LOOKALIKE should never be copied by the client"}, 400)
            err = self._check_jwt(form.get("assertion", "")) if grant == "urn:ietf:params:oauth:grant-type:jwt-bearer" else self._check_refresh(form) if grant == "refresh_token" else "unsupported_grant_type"
            if err:
                return JSONResponse({"error": err}, 400)
            tok = f"ya29.mock-{len(self.issued) + 1}"
            self.issued[tok] = self.clock() + self.lifetime
            return {"access_token": tok, "expires_in": self.lifetime, "token_type": "Bearer", "scope": "https://www.googleapis.com/auth/drive.readonly"}

    def _check_refresh(self, form: dict) -> str:
        known = self.refresh_tokens.get(form.get("refresh_token", ""))
        if known is None:
            return "invalid_grant"
        return "" if known == (form.get("client_id"), form.get("client_secret")) else "invalid_client"

    def _check_jwt(self, jwt: str) -> str:
        try:
            h, c, sig = jwt.split(".")
            header, claims = json.loads(_b64d(h)), json.loads(_b64d(c))
            key = self.service_accounts[claims["iss"]]
            key.verify(_b64d(sig), f"{h}.{c}".encode(), padding.PKCS1v15(), hashes.SHA256())  # type: ignore[attr-defined]
        except (ValueError, KeyError, InvalidSignature):
            return "invalid_grant"
        ok = header.get("alg") == "RS256" and claims.get("aud") == self.audience and claims.get("scope") and 0 < claims["exp"] - claims["iat"] <= 3600 and abs(claims["iat"] - self.clock()) <= 300
        return "" if ok else "invalid_grant"

    def valid(self, authorization: str | None) -> bool:
        tok = (authorization or "").removeprefix("Bearer ")
        return tok in self.issued and self.clock() < self.issued[tok]


class DriveMock:
    def __init__(self, token="dr-mock-token", issuer: GoogleTokenMock | None = None, page_size: int = 100):
        self.token, self.issuer, self.page_size = token, issuer, page_size
        self.files = {}  # id -> {"name","mimeType","text"}, and optionally "parents": [folder ids] and "trashed": True
        self.hits: list[str] = []
        self.queries: list[str] = []
        self.app = FastAPI()

        @self.app.get("/drive/v3/files")
        def lst(fields: str = "", pageToken: str = "", q: str = "", authorization: str | None = Header(default=None)):
            self.hits.append("list")
            self.queries.append(q)
            if not self._ok(authorization):
                return JSONResponse({"error": {"code": 401}}, 401)
            ids = [i for i, f in self.files.items() if self._matches(f, q)]
            start = int(pageToken) if pageToken else 0
            page = ids[start : start + self.page_size]
            body = {"files": [{"id": i, "name": self.files[i]["name"], "mimeType": self.files[i]["mimeType"], "modifiedTime": "2026-11-01T00:00:00Z"} for i in page]}
            if start + self.page_size < len(ids):
                body["nextPageToken"] = str(start + self.page_size)
            return body

        @self.app.get("/drive/v3/files/{fid}/export")
        def export(fid: str, mimeType: str = "text/plain", authorization: str | None = Header(default=None)):
            self.hits.append("export")
            if not self._ok(authorization):
                return JSONResponse({"error": {"code": 401}}, 401)
            return PlainTextResponse(self.files[fid]["text"]) if fid in self.files else JSONResponse({"error": {"code": 404}}, 404)

        @self.app.get("/drive/v3/files/{fid}")
        def media(fid: str, alt: str = "", authorization: str | None = Header(default=None)):
            self.hits.append("media")
            if not self._ok(authorization):
                return JSONResponse({"error": {"code": 401}}, 401)
            return PlainTextResponse(self.files[fid]["text"]) if fid in self.files and alt == "media" else JSONResponse({"error": {"code": 404}}, 404)

    @staticmethod
    def _matches(f: dict, q: str) -> bool:
        """The two query parts Lorefern sends: `'<folder id>' in parents` and `trashed = false` (a real Drive lists trashed files unless asked not to)."""
        parent = re.search(r"'([^']+)' in parents", q)
        if parent and parent.group(1) not in f.get("parents", []):
            return False
        return not ("trashed = false" in q and f.get("trashed"))

    def _ok(self, authorization: str | None) -> bool:
        return self.issuer.valid(authorization) if self.issuer else authorization == f"Bearer {self.token}"


class NotionMock:
    def __init__(self, token="nt-mock-token"):
        self.token, self.pages = token, {}  # id -> {"title","blocks":[str]}
        self.app = FastAPI()

        @self.app.post("/v1/search")
        def search(authorization: str | None = Header(default=None)):
            if authorization != f"Bearer {self.token}":
                return JSONResponse({"object": "error", "status": 401}, 401)
            return {"results": [{"object": "page", "id": i, "last_edited_time": "2026-11-01T00:00:00Z", "parent": {"type": "page_id", "page_id": p["parent"]} if p.get("parent") else {"type": "workspace"}, "properties": {"title": {"title": [{"plain_text": p["title"]}]}}} for i, p in self.pages.items()], "has_more": False}

        @self.app.get("/v1/blocks/{pid}/children")
        def children(pid: str, authorization: str | None = Header(default=None)):
            if authorization != f"Bearer {self.token}":
                return JSONResponse({"object": "error", "status": 401}, 401)
            return {"results": [{"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": b}]}} for b in self.pages.get(pid, {}).get("blocks", [])], "has_more": False}
