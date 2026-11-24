"""How Lorefern uses the shared base 1.2.0: the viewer role, approvals with two people, the sign in burst and the model switch."""

import json

import pytest
from fastapi.testclient import TestClient

from conftest import login, make_ctx
from lorefern import visibility
from lorefern.api.app import create_app
from lorefern.offline_llm import OfflineBackend
from sendora_core.auth import WRITE_ROLES, read_session_token
from sendora_core.llm import LLMError


def test_read_only_audiences_sign_in_with_the_base_viewer_role(client):
    roles = {}
    for who in ("owner@example.test", "approver@example.test", "finance@example.test", "staff@example.test"):
        token = client.post("/api/auth/login", json={"email": who, "password": "demo-password-1"}).json()["token"]
        roles[who] = read_session_token("test-secret-test-secret", token)["role"]
    assert roles == {"owner@example.test": "owner", "approver@example.test": "approver", "finance@example.test": "viewer", "staff@example.test": "viewer"}
    assert "viewer" not in WRITE_ROLES


def test_unknown_audience_gets_the_viewer_role_never_a_wider_one():
    assert visibility.session_role("nobody") == "viewer" and visibility.session_role("leadership") == "approver"


def test_a_second_person_decides_what_the_first_asked_for(client):
    o = login(client)
    client.post("/api/reminders/plan", headers=o)
    rem = client.get("/api/reminders", headers=o).json()
    for _ in range(7):
        if rem:
            break
        client.post("/api/demo/advance", headers=o, json={"hours": 24})
        client.post("/api/reminders/plan", headers=o)
        rem = client.get("/api/reminders", headers=o).json()
    assert rem
    ap = client.post("/api/reminders/request-send", headers=o, json={"ids": [rem[0]["id"]]}).json()["approval_id"]
    own = client.post(f"/api/approvals/{ap}/decide", headers=o, json={"approve": True})
    assert own.status_code == 409 and "someone else must decide" in own.text
    lead = login(client, "approver@example.test")
    assert client.post(f"/api/approvals/{ap}/decide", headers=lead, json={"approve": False}).json() == {"status": "rejected"}
    # the other direction: leadership asks, the owner decides
    ap2 = client.post("/api/reminders/request-send", headers=lead, json={"ids": [rem[0]["id"]]}).json()["approval_id"]
    assert client.post(f"/api/approvals/{ap2}/decide", headers=lead, json={"approve": True}).status_code == 409
    assert client.post(f"/api/approvals/{ap2}/decide", headers=o, json={"approve": False}).json() == {"status": "rejected"}


def test_login_burst_comes_from_settings(tmp_path):
    ctx = make_ctx(tmp_path, login_burst=2)
    with TestClient(create_app(ctx.settings, ctx)) as c:
        codes = [c.post("/api/auth/login", json={"email": "owner@example.test", "password": "x"}).status_code for _ in range(4)]
    assert codes[:2] == [401, 401] and codes[2:] == [429, 429]


def test_llm_switch_defaults_to_the_offline_stand_in_and_keeps_the_model_shape(ctx):
    passages = json.dumps([[7, "We keep invoices for seven years. Lunch is at noon."]])
    with ctx.factory() as s:
        llm = ctx.llm(s)
        assert isinstance(llm.backend, OfflineBackend) and llm.backend.is_live is False
        raw = llm.ask('[task:write_answer]\nKEY_WORDS: [["invoic", 1.0], ["keep", 0.6]]', purpose="answer", untrusted={"question": "How long do we keep invoices?", "passages": passages})
    data = json.loads(raw)
    assert data["sentences"] and data["sentences"][0]["passage_ids"] == [7] and "seven years" in data["sentences"][0]["text"] and data["cannot_answer"] is False


def test_llm_backend_anthropic_without_a_key_fails_loudly(tmp_path):
    ctx = make_ctx(tmp_path, llm_backend="anthropic", anthropic_api_key=None)  # explicit None: the shell may hold a real key
    with ctx.factory() as s, pytest.raises(LLMError):
        ctx.llm(s)
