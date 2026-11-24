"""Drive sign in with token refresh, against a LOCAL fake Google token service and a fake Drive. Nothing here reaches Google (UNVERIFIED live)."""

import base64
import json
import logging

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi.testclient import TestClient

from lorefern.adapters.drive_auth import EARLY, DriveTokenProvider, sign_jwt
from lorefern.adapters.sources import DriveSource
from lorefern.config import Settings
from mock.source_mocks import DriveMock, FakeClock, GoogleTokenMock
from sendora_core.adapters import AdapterError

EMAIL = "reader@lorefern-test.iam.example"
SECRET_WORDS = ["PRIVATE-KEY-MARKER", "client-secret-value-123", "refresh-token-value-456", "static-token-value-789"]


def make_key(email=EMAIL):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    return key.public_key(), json.dumps({"type": "service_account", "client_email": email, "private_key": pem, "private_key_id": "k1"})


def settings(**kw):
    return Settings(_env_file=None, drive_token_uri="http://testserver/token", **kw)


class World:
    def __init__(self, **kw):
        self.clock = FakeClock()
        self.token = GoogleTokenMock(self.clock, **kw)
        self.drive = DriveMock(issuer=self.token, page_size=2)
        self.token_client, self.drive_client = TestClient(self.token.app), TestClient(self.drive.app)

    def source(self, s: Settings) -> DriveSource:
        auth = DriveTokenProvider(s, client=self.token_client, clock=self.clock)
        return DriveSource(s, client=self.drive_client, auth=auth)


@pytest.fixture()
def world():
    w = World()
    w.drive.files = {
        "d1": {"name": "Leave policy", "mimeType": "application/vnd.google-apps.document", "text": "Staff get 25 days of leave."},
        "d2": {"name": "Notes", "mimeType": "text/plain", "text": "Plain text file."},
        "d3": {"name": "Sheet", "mimeType": "application/vnd.google-apps.spreadsheet", "text": "ignored"},
        "d4": {"name": "Expenses", "mimeType": "application/vnd.google-apps.document", "text": "Expenses over 500 need approval."},
        "d5": {"name": "Hiring", "mimeType": "application/vnd.google-apps.document", "text": "Two interviews."},
    }
    return w


def sa_world(world):
    pub, key_json = make_key()
    world.token.service_accounts[EMAIL] = pub
    return settings(drive_service_account_json=key_json), key_json


def test_service_account_signs_in_pages_and_reads_documents(world):
    s, _ = sa_world(world)
    docs = world.source(s).list_documents()
    assert [d.title for d in docs] == ["Leave policy", "Notes", "Expenses", "Hiring"]  # the spreadsheet is skipped, 3 pages of 2 files
    assert docs[1].text == "Plain text file." and docs[0].updated_on == "2026-11-01"
    assert len(world.token.requests) == 1  # one token for all the calls


def test_token_is_reused_then_renewed_before_it_expires(world):
    s, _ = sa_world(world)
    src = world.source(s)
    src.list_documents()
    world.clock.advance(3600 - EARLY - 5)
    src.list_documents()
    assert len(world.token.requests) == 1
    world.clock.advance(10)  # now inside the early window
    src.list_documents()
    assert len(world.token.requests) == 2 and len(set(world.token.issued)) == 2


def test_oauth_refresh_token_path(world):
    world.token.refresh_tokens["refresh-token-value-456"] = ("client-id-1", "client-secret-value-123")
    s = settings(drive_client_id="client-id-1", drive_client_secret="client-secret-value-123", drive_refresh_token="refresh-token-value-456")
    src = world.source(s)
    assert src.auth.mode == "oauth_refresh" and len(src.list_documents()) == 4
    world.clock.advance(4000)
    assert len(src.list_documents()) == 4 and [r["grant"] for r in world.token.requests] == ["refresh_token", "refresh_token"]


def test_a_refused_request_renews_the_token_once_and_retries(world):
    s, _ = sa_world(world)
    src = world.source(s)
    src.list_documents()
    world.token.issued.clear()  # the server forgets the token (revoked, rotated) while ours has not expired
    assert len(src.list_documents()) == 4
    assert len(world.token.requests) == 2


def test_a_second_refusal_is_reported_not_looped(world):
    s, _ = sa_world(world)
    src = world.source(s)
    src.list_documents()
    world.drive.issuer = GoogleTokenMock(world.clock)  # a Drive that accepts none of our tokens
    n = len(world.drive.hits)
    with pytest.raises(AdapterError, match="refused the access"):
        src.list_documents()
    assert len(world.drive.hits) - n == 2  # one try, one retry, then stop


def test_revoked_refresh_token_is_explained_without_leaking(world, caplog):
    caplog.set_level(logging.DEBUG)
    world.token.refresh_tokens["refresh-token-value-456"] = ("client-id-1", "client-secret-value-123")
    s = settings(drive_client_id="client-id-1", drive_client_secret="client-secret-value-123", drive_refresh_token="refresh-token-value-456")
    src = world.source(s)
    src.list_documents()
    world.token.mode = "invalid_grant"
    world.clock.advance(4000)
    ok, detail = src.healthcheck()
    assert ok is False and "invalid_grant" in detail and "give consent again" in detail
    for w in SECRET_WORDS + ["SECRET-LOOKALIKE"]:
        assert w not in detail and w not in caplog.text and w not in repr(s)


def test_service_account_disabled_and_wrong_client_messages(world):
    s, _ = sa_world(world)
    src = world.source(s)
    world.token.mode = "invalid_grant"
    with pytest.raises(AdapterError, match="key was disabled or deleted"):
        src.list_documents()
    world.token.mode = "invalid_client"
    with pytest.raises(AdapterError, match="invalid_client"):
        src.list_documents()


def test_unknown_service_account_is_refused_by_the_token_service(world):
    _, key_json = make_key("stranger@lorefern-test.iam.example")
    with pytest.raises(AdapterError, match="invalid_grant"):
        world.source(settings(drive_service_account_json=key_json)).list_documents()


def test_token_service_down_gives_a_retry_message(world):
    s, _ = sa_world(world)
    world.token.mode = "server_error"
    with pytest.raises(AdapterError, match="503"):
        world.source(s).list_documents()

    def boom(request):
        raise httpx.ConnectError("no route")

    pub, key_json = make_key()
    auth = DriveTokenProvider(settings(drive_service_account_json=key_json), client=httpx.Client(transport=httpx.MockTransport(boom)))
    with pytest.raises(AdapterError, match="Could not reach the Google token service"):
        auth.token()


def test_answer_without_expires_in_is_treated_as_short_lived():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json={"access_token": "ya29.x"})

    clock = FakeClock()
    _, key_json = make_key()
    auth = DriveTokenProvider(settings(drive_service_account_json=key_json), client=httpx.Client(transport=httpx.MockTransport(handler)), clock=clock)
    auth.token(); auth.token()
    assert len(calls) == 1
    clock.advance(200)
    auth.token()
    assert len(calls) == 2


def test_assertion_follows_googles_documented_shape():
    pub, key_json = make_key()
    jwt = sign_jwt(json.loads(key_json), "https://www.googleapis.com/auth/drive.readonly", 1_800_000_000, "https://oauth2.googleapis.com/token", "boss@example.test")
    h, c, _ = jwt.split(".")
    dec = lambda p: json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))  # noqa: E731
    assert dec(h) == {"alg": "RS256", "typ": "JWT", "kid": "k1"}
    claims = dec(c)
    assert claims == {"iss": EMAIL, "scope": "https://www.googleapis.com/auth/drive.readonly", "aud": "https://oauth2.googleapis.com/token", "iat": 1_800_000_000, "exp": 1_800_003_600, "sub": "boss@example.test"}


def test_bad_keys_fail_at_start_with_plain_words():
    for bad in ["not json", json.dumps({"client_email": "a@b"}), json.dumps({"client_email": "a@b", "private_key": "-----BEGIN " + "PRIVATE KEY-----\nPRIVATE-KEY-MARKER\n-----END " + "PRIVATE KEY-----"})]:
        with pytest.raises(AdapterError) as e:
            DriveTokenProvider(settings(drive_service_account_json=bad), client=httpx.Client())
        assert "PRIVATE-KEY-MARKER" not in str(e.value)
    ec_key = ec.generate_private_key(ec.SECP256R1())
    pem = ec_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    with pytest.raises(AdapterError, match="RSA"):
        DriveTokenProvider(settings(drive_service_account_json=json.dumps({"client_email": "a@b", "private_key": pem})), client=httpx.Client())


def test_key_file_path_works_and_a_missing_file_is_explained(tmp_path):
    _, key_json = make_key()
    f = tmp_path / "key.json"
    f.write_text(key_json)
    assert DriveTokenProvider(settings(drive_service_account_file=str(f)), client=httpx.Client()).mode == "service_account"
    with pytest.raises(AdapterError, match="could not be read"):
        DriveTokenProvider(settings(drive_service_account_file=str(tmp_path / "missing.json")), client=httpx.Client())


def test_static_token_cannot_be_renewed_and_says_so(world):
    s = settings(drive_token="static-token-value-789")
    src = world.source(s)
    assert src.auth.mode == "static" and not src.auth.can_refresh
    with pytest.raises(AdapterError, match="refused the access"):
        src.list_documents()
    assert len(world.drive.hits) == 1  # no retry loop for a token that cannot be renewed
    assert len(world.token.requests) == 0


def test_no_sign_in_details_at_all_is_a_plain_error():
    with pytest.raises(AdapterError, match="DRIVE_SERVICE_ACCOUNT_JSON"):
        DriveTokenProvider(settings(), client=httpx.Client())
    assert settings().drive_credentials() is False


def test_token_address_must_be_https_and_public_when_no_client_is_given():
    _, key_json = make_key()
    with pytest.raises(AdapterError, match="https"):
        DriveTokenProvider(Settings(_env_file=None, drive_service_account_json=key_json, drive_token_uri="http://127.0.0.1:9/token"))


def test_secrets_never_appear_in_logs_or_settings_repr(world, caplog):
    caplog.set_level(logging.DEBUG)
    pub, key_json = make_key()
    world.token.service_accounts[EMAIL] = pub
    s = settings(drive_service_account_json=key_json, drive_client_secret="client-secret-value-123", drive_refresh_token="refresh-token-value-456")
    world.source(s).list_documents()
    private_pem = json.loads(key_json)["private_key"].splitlines()[1]
    for text in (caplog.text, repr(s)):
        assert private_pem not in text and "client-secret-value-123" not in text and "refresh-token-value-456" not in text
    assert "ya29.mock" not in caplog.text
