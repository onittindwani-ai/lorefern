"""Google Drive sign in that keeps working: a service account key or an OAuth refresh token, with token refresh and expiry.

Three ways to give Lorefern access, picked by which variables are set (the first one found wins):

1. `service_account`: DRIVE_SERVICE_ACCOUNT_JSON (the key file's text) or DRIVE_SERVICE_ACCOUNT_FILE (a path to it). Lorefern signs a short lived
   JWT with the key (RS256) and trades it for an access token at the Google token address. The service account only sees files someone shared with its email.
2. `oauth_refresh`: DRIVE_CLIENT_ID, DRIVE_CLIENT_SECRET and DRIVE_REFRESH_TOKEN from a one time consent. The refresh token is traded for an access token.
3. `static`: DRIVE_TOKEN, a single access token. It expires after about an hour and cannot be renewed. For a first try only.

An access token is kept in memory with its expiry and renewed two minutes early. A refused request (401) renews it once and retries once. Secrets come from the
environment only. Nothing here logs, prints or puts a secret in an error message: failures are reported with Google's short error code only.

Written from Google's public documentation (service account and web server OAuth pages, read 2026-11-23) and tested against a local fake token server only.
UNVERIFIED against the real Google token service and the real Drive API until a client uses it.
"""

from __future__ import annotations

import base64
import json
import threading
import time
from collections.abc import Callable
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from lorefern.adapters.base import safe_base_url
from sendora_core.adapters import AdapterError

JWT_GRANT = "urn:ietf:params:oauth:grant-type:jwt-bearer"
EARLY = 120  # seconds before the real expiry at which a token is renewed
DEFAULT_LIFETIME = 300  # used when the answer has no usable expires_in; short on purpose
KNOWN_ERRORS = {"invalid_grant", "invalid_client", "invalid_request", "unauthorized_client", "invalid_scope", "access_denied", "disabled_client", "invalid_rapt"}


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def sign_jwt(key: dict, scope: str, now: float, token_uri: str, subject: str = "") -> str:
    """The signed assertion for a service account (RS256, one hour at most)."""
    try:
        private = serialization.load_pem_private_key(str(key["private_key"]).encode(), password=None)
        email = str(key["client_email"])
    except (KeyError, ValueError, TypeError) as exc:
        raise AdapterError("The service account key is not valid. It needs client_email and private_key. Download a new JSON key.") from exc
    header = {"alg": "RS256", "typ": "JWT", **({"kid": key["private_key_id"]} if key.get("private_key_id") else {})}
    claims = {"iss": email, "scope": scope, "aud": token_uri, "iat": int(now), "exp": int(now) + 3600, **({"sub": subject} if subject else {})}
    body = f"{_b64(json.dumps(header, separators=(',', ':')).encode())}.{_b64(json.dumps(claims, separators=(',', ':')).encode())}"
    try:
        sig = private.sign(body.encode(), padding.PKCS1v15(), hashes.SHA256())  # type: ignore[union-attr]
    except (TypeError, AttributeError) as exc:
        raise AdapterError("The service account private key must be an RSA key. Download a new JSON key.") from exc
    return f"{body}.{_b64(sig)}"


class DriveTokenProvider:
    def __init__(self, settings, client: httpx.Client | None = None, clock: Callable[[], float] = time.time):
        self.settings, self.clock = settings, clock
        self._lock = threading.Lock()
        self._token = ""
        self._expires_at = 0.0
        self._key: dict | None = None
        self.mode = self._pick()
        self.token_uri = settings.drive_token_uri
        if client is not None:
            self._client = client
        else:
            if self.mode in {"service_account", "oauth_refresh"}:
                safe_base_url(self.token_uri)  # refuse a private or non web address before any secret is sent
            self._client = httpx.Client(timeout=30)
        if self.mode == "service_account":
            self._key = self._load_key()
        if self.mode == "static":
            self._token = settings.drive_token

    def _pick(self) -> str:
        s = self.settings
        if s.drive_service_account_json or s.drive_service_account_file:
            return "service_account"
        if s.drive_client_id and s.drive_client_secret and s.drive_refresh_token:
            return "oauth_refresh"
        if s.drive_token:
            return "static"
        raise AdapterError("Google Drive needs DRIVE_SERVICE_ACCOUNT_JSON, or DRIVE_CLIENT_ID with DRIVE_CLIENT_SECRET and DRIVE_REFRESH_TOKEN, or DRIVE_TOKEN.")

    def _load_key(self) -> dict:
        s = self.settings
        try:
            raw = s.drive_service_account_json or Path(s.drive_service_account_file).read_text()
            key = json.loads(raw)
        except (OSError, ValueError) as exc:
            raise AdapterError("The service account key could not be read. Check DRIVE_SERVICE_ACCOUNT_JSON or DRIVE_SERVICE_ACCOUNT_FILE.") from exc
        if not isinstance(key, dict) or not key.get("client_email") or not key.get("private_key"):
            raise AdapterError("The service account key is not valid. It needs client_email and private_key. Download a new JSON key.")
        sign_jwt(key, "x", 0, "x")  # fail at start, not at the first sync, when the private key is not usable
        return key

    @property
    def can_refresh(self) -> bool:
        return self.mode in {"service_account", "oauth_refresh"}

    def invalidate(self) -> None:
        with self._lock:
            if self.can_refresh:
                self._token, self._expires_at = "", 0.0

    def token(self) -> str:
        with self._lock:
            if self.mode == "static":
                return self._token
            if self._token and self.clock() < self._expires_at - EARLY:
                return self._token
            self._token, self._expires_at = self._fetch()
            return self._token

    def _fetch(self) -> tuple[str, float]:
        s, now = self.settings, self.clock()
        if self.mode == "service_account":
            assert self._key is not None
            form = {"grant_type": JWT_GRANT, "assertion": sign_jwt(self._key, s.drive_scope, now, self.token_uri, s.drive_subject)}
        else:
            form = {"grant_type": "refresh_token", "client_id": s.drive_client_id, "client_secret": s.drive_client_secret, "refresh_token": s.drive_refresh_token}
        try:
            r = self._client.post(self.token_uri, data=form, headers={"Accept": "application/json"})
        except httpx.HTTPError as exc:
            raise AdapterError(f"Could not reach the Google token service ({type(exc).__name__}). Try again in a minute.") from exc
        if r.status_code >= 500:
            raise AdapterError(f"The Google token service answered {r.status_code}. Try again in a minute.")
        data = self._json(r)
        if r.status_code != 200:
            code = str(data.get("error", "")) if isinstance(data, dict) else ""
            code = code if code in KNOWN_ERRORS else "unknown_error"
            raise AdapterError(self._explain(code))
        tok = data.get("access_token") if isinstance(data, dict) else None
        if not isinstance(tok, str) or not tok:
            raise AdapterError("The Google token service answered without an access token.")
        life = data.get("expires_in")
        life = float(life) if isinstance(life, (int, float)) and 0 < life <= 86400 else DEFAULT_LIFETIME
        return tok, now + life

    @staticmethod
    def _json(r: httpx.Response):
        try:
            return r.json()
        except ValueError:
            return {}

    def _explain(self, code: str) -> str:
        if code == "invalid_grant":
            who = "the service account key was disabled or deleted, or the clock on this server is wrong" if self.mode == "service_account" else "the refresh token was revoked or expired, so the person must give consent again"
            return f"Google refused to give a new access token (invalid_grant): {who}. See docs/03-CONNECT-YOUR-TOOLS.md."
        if code in {"invalid_client", "unauthorized_client", "disabled_client"}:
            return f"Google refused the sign in details ({code}). Check DRIVE_CLIENT_ID and DRIVE_CLIENT_SECRET, or that the service account may use the Drive API."
        return f"Google refused to give a new access token ({code}). See docs/03-CONNECT-YOUR-TOOLS.md."
