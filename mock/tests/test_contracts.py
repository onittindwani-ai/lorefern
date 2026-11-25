"""Contract tests: the adapters against excerpts saved in mock/contracts/ (each SOURCE.txt says what was read, when, and what could not be fetched).

No machine readable spec could be fetched for any vendor here (page text only), so the excerpts are the field lists and examples read from the vendor pages on 2026-11-23.
Nothing ran against a real service.
"""

import base64
import json
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs

import httpx
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives import hashes, serialization

from lorefern.adapters.drive_auth import JWT_GRANT, DriveTokenProvider
from lorefern.adapters.meetings import FathomMeetings, FirefliesMeetings
from lorefern.adapters.slack import read_export
from lorefern.adapters.smtp import SmtpEmail
from lorefern.adapters.sources import DriveSource, NotionSource
from lorefern.config import Settings
from sendora_core.settings import Mode

C = Path(__file__).resolve().parents[1] / "contracts"


def load(vendor, name):
    return json.loads((C / vendor / name).read_text(encoding="utf-8"))


def unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def test_every_contract_folder_says_where_it_came_from_and_when():
    assert {d.name for d in C.iterdir() if d.is_dir()} == {"google_drive", "fireflies", "fathom", "notion", "slack_export", "smtp_imap"}
    for d in C.iterdir():
        text = (d / "SOURCE.txt").read_text(encoding="utf-8")
        assert "2026-11-23" in text and ("http" in text or d.name == "smtp_imap")


# ---- Google: the documented token endpoint request shapes
def sa_settings(token_uri):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    sa = json.dumps({"type": "service_account", "client_email": "reader@x.iam.example", "private_key": pem, "private_key_id": "k1"})
    return key.public_key(), Settings(_env_file=None, drive_service_account_json=sa, drive_token_uri=token_uri)


def test_the_service_account_token_request_follows_the_documented_shape():
    doc, seen = load("google_drive", "token_requests.json"), {}

    def handler(req):
        seen["m"], seen["url"], seen["ct"], seen["form"] = req.method, str(req.url), req.headers["content-type"], {k: v[0] for k, v in parse_qs(req.content.decode()).items()}
        return httpx.Response(200, json={"access_token": "ya29.x", "expires_in": 3600, "token_type": "Bearer", "scope": "s"})

    pub, s = sa_settings(doc["endpoint"])
    now = time.time()
    tok = DriveTokenProvider(s, client=httpx.Client(transport=httpx.MockTransport(handler)), clock=lambda: now).token()
    assert tok == "ya29.x" and seen["m"] == doc["method"] and seen["url"] == doc["endpoint"] and seen["ct"].startswith(doc["content_type"])
    sa = doc["service_account"]
    assert set(seen["form"]) == set(sa["form_fields"]) and seen["form"]["grant_type"] == sa["grant_type"] == JWT_GRANT
    head, claims, sig = seen["form"]["assertion"].split(".")
    header, body = json.loads(unb64(head)), json.loads(unb64(claims))
    assert header["alg"] == sa["jwt_header"]["alg"] and header["typ"] == sa["jwt_header"]["typ"]
    assert set(sa["claims_required"]) <= set(body) <= set(sa["claims_required"]) | set(sa["claims_optional"])
    assert body["aud"] == sa["aud"] and body["iss"] == "reader@x.iam.example" and body["exp"] - body["iat"] <= sa["max_lifetime_seconds"]
    pub.verify(unb64(sig), f"{head}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256())  # RS256 signature is valid


def test_the_refresh_token_request_follows_the_documented_shape_and_uses_the_response_fields():
    doc, seen = load("google_drive", "token_requests.json"), {}

    def handler(req):
        seen["form"], seen["ct"], seen["url"] = {k: v[0] for k, v in parse_qs(req.content.decode()).items()}, req.headers["content-type"], str(req.url)
        return httpx.Response(200, json={"access_token": "ya29.r", "expires_in": 3920, "scope": "s", "token_type": "Bearer"})

    s = Settings(_env_file=None, drive_client_id="cid", drive_client_secret="csec", drive_refresh_token="rtok", drive_token_uri=doc["endpoint"])
    assert DriveTokenProvider(s, client=httpx.Client(transport=httpx.MockTransport(handler))).token() == "ya29.r"
    r = doc["refresh"]
    assert seen["url"] == doc["endpoint"] and seen["ct"].startswith(doc["content_type"]) and seen["form"]["grant_type"] == r["grant_type"]
    assert set(r["form_fields_required"]) <= set(seen["form"]) <= set(r["form_fields_required"]) | set(r["form_fields_optional"])
    assert set(doc["response_fields"]) >= {"access_token", "expires_in"}


def test_drive_calls_carry_the_bearer_token_of_the_documented_type():
    seen = []

    def drive(req):
        seen.append((req.url.path, req.headers.get("authorization"), dict(req.url.params)))
        return httpx.Response(200, json={"files": []})

    s = Settings(_env_file=None, drive_token="ya29.static")
    DriveSource(s, client=httpx.Client(base_url="https://www.googleapis.com", transport=httpx.MockTransport(drive))).list_documents()
    assert seen[0][0] == "/drive/v3/files" and seen[0][1] == "Bearer ya29.static" and seen[0][2]["pageSize"] == "100"


# ---- Fireflies and Fathom
def live(**kw):
    base = dict(mode=Mode.LIVE, kill_switch=False, fireflies_token="ff-key", fireflies_base_url="https://api.fireflies.ai", fathom_token="fa-key", fathom_base_url="https://api.fathom.ai", notion_token="nt", notion_base_url="https://api.notion.com")
    base.update(kw)
    return SimpleNamespace(**base)


def test_fireflies_request_uses_the_documented_endpoint_header_and_fields():
    doc, seen = load("fireflies", "request.json"), {}

    def handler(req):
        seen["m"], seen["url"], seen["auth"], seen["q"] = req.method, str(req.url), req.headers["authorization"], json.loads(req.content)["query"]
        return httpx.Response(200, json={"data": {"transcripts": [{"id": "t1", "title": "Weekly", "date": 1772438400000, "participants": ["a@x.test"], "sentences": [{"speaker_name": "Dev", "text": "I will send it."}], "summary": {"action_items": "**Dev**\nSend it"}}]}})

    ms = FirefliesMeetings(live(), httpx.Client(base_url="https://api.fireflies.ai", transport=httpx.MockTransport(handler))).list_meetings()
    assert seen["m"] == doc["method"] and seen["url"] == doc["url"] and seen["auth"] == "Bearer ff-key"
    for f in doc["query_fields"]["transcripts"] + doc["query_fields"]["sentences"] + doc["query_fields"]["summary"]:
        assert f in seen["q"]
    assert set(doc["query_fields"]["sentences"]) <= set(doc["documented_sentence_fields"]) and set(doc["query_fields"]["summary"]) <= set(doc["documented_summary_fields"])
    assert ms[0].lines == [("Dev", "I will send it.")] and ms[0].held_on == "2026-03-02"


def test_fathom_request_and_parsing_follow_the_documented_example():
    doc, seen = load("fathom", "list_meetings.json"), []

    def handler(req):
        seen.append((req.method, req.url.path, req.headers["x-api-key"], dict(req.url.params)))
        return httpx.Response(200, json=doc["response_example"] if len(seen) == 1 else {"items": [], "next_cursor": None})

    ms = FathomMeetings(live(), httpx.Client(base_url=doc["base"].rsplit("/external", 1)[0], transport=httpx.MockTransport(handler))).list_meetings()
    m, path, key, params = seen[0]
    assert m == doc["method"] and path == "/external/v1" + doc["path"] and key == "fa-key" and set(params) <= set(doc["query"])
    assert params["include_transcript"] == "true" and params["include_action_items"] == "true"
    assert len(seen) == 2 and seen[1][3]["cursor"] == doc["response_example"]["next_cursor"]  # the cursor is sent back
    assert ms[0].external_id == "123456789" and ms[0].lines == [("Alice Johnson", "Let us begin.")] and ms[0].held_on == "2025-03-01"


# ---- Notion
def test_notion_search_follows_the_documented_request_and_pages_through_the_cursor():
    doc, seen = load("notion", "search.json"), []

    def handler(req):
        if req.url.path == "/v1/search":
            body = json.loads(req.content)
            seen.append((req.method, req.headers, body))
            if "start_cursor" not in body:
                return httpx.Response(200, json={"object": "list", "results": [{"id": "p1", "object": "page", "properties": {"title": {"title": [{"plain_text": "One"}]}}, "last_edited_time": "2026-01-01T00:00:00Z"}], "next_cursor": "c2", "has_more": True})
            return httpx.Response(200, json={"object": "list", "results": [{"id": "p2", "object": "page", "properties": {"title": {"title": [{"plain_text": "Two"}]}}, "last_edited_time": "2026-01-02T00:00:00Z"}], "next_cursor": None, "has_more": False})
        return httpx.Response(200, json={"results": [{"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "Body."}]}}]})

    docs = NotionSource(live(), httpx.Client(base_url="https://api.notion.com", transport=httpx.MockTransport(handler))).list_documents()
    assert [d.title for d in docs] == ["One", "Two"] and len(seen) == 2
    m, h, body = seen[0]
    assert m == doc["method"] and h["authorization"] == "Bearer nt" and h["notion-version"] == doc["notion_version"] and set(body) <= set(doc["body_optional"])
    assert body["filter"] == doc["filter_example"] and seen[1][2]["start_cursor"] == "c2"


# ---- Slack export
def test_the_slack_export_reader_handles_the_documented_message_record(tmp_path):
    doc = load("slack_export", "message.json")
    (tmp_path / "users.json").write_text(json.dumps([{"id": doc["message_example"]["user"], "real_name": "Dev Raghunathan"}]))
    (tmp_path / "channels.json").write_text(json.dumps([{"id": "C1", "name": "ops"}]))
    (tmp_path / "ops").mkdir()
    (tmp_path / "ops" / "2026-03-02.json").write_text(json.dumps([doc["message_example"], {"type": "message", "subtype": "channel_join", "user": "U9", "text": "joined", "ts": "1"}]))
    days = read_export(tmp_path)
    assert [(d.channel, d.day, d.text) for d in days] == [("ops", "2026-03-02", "Dev Raghunathan: Hello world")]


# ---- mail
def test_a_reminder_message_has_the_rfc_5322_header_fields(monkeypatch):
    sent, started = [], []

    class FakeSmtp:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self, context=None): started.append(context)
        def login(self, *a): pass
        def send_message(self, m): sent.append(m)

    monkeypatch.setattr("smtplib.SMTP", FakeSmtp)
    s = Settings(_env_file=None, mode=Mode.LIVE, demo_mode=False, smtp_host="smtp.example.test", smtp_user="u", smtp_password="p", email_from="lorefern@example.test")
    mid = SmtpEmail(s).send(to="dev@example.test", subject="Reminder", body="Hello")
    m = sent[0]
    assert m["From"] and m["To"] == "dev@example.test" and m["Subject"] == "Reminder" and m["Message-ID"] == mid and m["Message-ID"].startswith("<")
    assert started and started[0].verify_mode.name == "CERT_REQUIRED" and started[0].check_hostname  # the server's certificate and host name are checked
