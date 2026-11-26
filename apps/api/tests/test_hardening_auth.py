"""Sign in, the demo shortcuts, and the refusal to start on unsafe settings."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from conftest import DATA, login
from lorefern import demo
from lorefern.api import routes_auth
from lorefern.api.app import create_app
from lorefern.config import Settings
from lorefern.models import Owner, Source
from real_install import PASSWORD, PEOPLE, REAL_SECRET, Install, real_settings
from sendora_core.settings import ConfigError


def demo_settings(tmp_path, **kw):
    return Settings(database_url=f"sqlite:///{tmp_path / 'd.sqlite3'}", session_secret="test-secret-test-secret", seed_dir=DATA, _env_file=None, **kw)


def post(c, email, password):
    return c.post("/api/auth/login", json={"email": email, "password": password}).status_code


def test_login_key_ignores_spaces_and_capitals(tmp_path):
    c = TestClient(create_app(real_settings(tmp_path, login_burst=5)), base_url="http://api.test")
    variants = [PEOPLE["owner"], " " + PEOPLE["owner"], PEOPLE["owner"] + " ", PEOPLE["owner"].upper(), "\t" + PEOPLE["owner"], PEOPLE["owner"] + "\n"]
    codes = [post(c, v, "wrong-password") for v in variants]
    assert codes[:5] == [401] * 5 and codes[5] == 429  # the sixth try is refused whatever padding it uses


def test_login_accepts_a_padded_email_with_the_right_password(tmp_path):
    c = TestClient(create_app(real_settings(tmp_path)), base_url="http://api.test")
    r = c.post("/api/auth/login", json={"email": "  " + PEOPLE["owner"].upper() + " ", "password": PASSWORD})
    assert r.status_code == 200 and r.json()["user"] == PEOPLE["owner"] and r.json()["role"] == "owner"


def test_login_refuses_oversize_fields(tmp_path):
    c = TestClient(create_app(real_settings(tmp_path)), base_url="http://api.test")
    assert post(c, "a" * 300 + "@x.test", "x") == 422
    assert post(c, PEOPLE["owner"], "x" * 2000) == 422


def test_each_address_has_its_own_wider_limit(tmp_path):
    c = TestClient(create_app(real_settings(tmp_path, login_burst=2)), base_url="http://api.test")
    codes = [post(c, f"user{i}@x.test", "x") for i in range(40)]  # a new email every time never gives a fresh set of tries
    assert codes[0] == 401 and 429 in codes[30:]


def test_guesses_spread_over_many_addresses_still_run_out(tmp_path):
    app = create_app(real_settings(tmp_path, login_burst=2))
    codes = []
    for i in range(30):
        c = TestClient(app, base_url="http://api.test", client=(f"203.0.113.{i + 1}", 50000 + i))
        codes.append(post(c, PEOPLE["owner"], "wrong-password"))
    assert codes[0] == 401 and 429 in codes[20:]
    other = TestClient(app, base_url="http://api.test", client=("198.51.100.5", 40000))
    assert post(other, "someone.else@example.test", "x") == 401  # other accounts are not affected


def test_unknown_accounts_cost_the_same_work_as_wrong_passwords(tmp_path, monkeypatch):
    calls = []
    real = routes_auth.verify_password_or_dummy
    monkeypatch.setattr(routes_auth, "verify_password_or_dummy", lambda pw, h: (calls.append(h), real(pw, h))[1])
    c = TestClient(create_app(real_settings(tmp_path)), base_url="http://api.test")
    assert post(c, "nobody@x.test", "x") == 401
    assert calls == [None]  # a hash check against a throw away hash was still done


def test_a_real_owner_password_switches_every_demo_shortcut_off_even_in_demo_mode(tmp_path):
    s = real_settings(tmp_path, demo_mode=True, knowledge_dir="")
    assert s.demo_shortcuts is False
    c = TestClient(create_app(s), base_url="http://api.test")
    for email in ("approver@example.test", "finance@example.test", "staff@example.test", "owner@example.test", PEOPLE["owner"], PEOPLE["staff"]):
        assert post(c, email, "demo-password-1") == 401, email
    c.headers["x-session"] = c.post("/api/auth/login", json={"email": PEOPLE["owner"], "password": PASSWORD}).json()["token"]
    assert c.post("/api/demo/reset").status_code == 404 and c.post("/api/demo/tick").status_code == 404 and c.post("/api/demo/stress-tasks", json={"n": 5}).status_code == 404
    assert c.get("/api/auth/me").json()["demo_mode"] is False  # the demo bar must not show buttons that answer 404
    assert any("OWNER_PASSWORD_HASH is set" in p for p in s.problems())
    with TestClient(create_app(s)).app.state.ctx.factory() as db:
        assert db.scalars(select(Owner)).first() is None  # a real install is never filled with the demo world


def test_the_sample_accounts_exist_only_in_a_demo_with_no_owner_password(tmp_path):
    c = TestClient(create_app(demo_settings(tmp_path)), base_url="http://api.test")
    for email, role in (("approver@example.test", "leadership"), ("finance@example.test", "finance"), ("staff@example.test", "staff"), ("owner@example.test", "owner")):
        r = c.post("/api/auth/login", json={"email": email, "password": "demo-password-1"})
        assert r.status_code == 200 and r.json()["role"] == role, email
    assert post(c, "owner@example.test", "not-the-password") == 401
    c.headers["x-session"] = login(c)["x-session"]
    assert c.get("/api/auth/me").json()["demo_mode"] is True


def test_a_member_without_a_password_hash_cannot_sign_in_with_the_demo_password(tmp_path):
    s = real_settings(tmp_path, members_json='{"nohash@acme.test": {"audience": "staff"}}')
    c = TestClient(create_app(s), base_url="http://api.test")
    assert post(c, "nohash@acme.test", "demo-password-1") == 401 and post(c, "nohash@acme.test", PASSWORD) == 401


def test_the_demo_reset_refuses_when_called_directly_with_an_owner_password(tmp_path):
    app = create_app(real_settings(tmp_path, demo_mode=True, knowledge_dir=""))
    ctx = app.state.ctx
    with ctx.factory() as session, pytest.raises(PermissionError):
        demo.reset(session, ctx)


def test_the_demo_reset_is_owner_only_and_leaves_a_database_with_real_sources_alone(client):
    assert client.post("/api/demo/reset", headers=login(client, "staff@example.test")).status_code == 403
    o = login(client)
    assert client.post("/api/sources", headers=o, json={"kind": "folder", "name": "Mine", "uri": "company/00 Governance", "default_tag": "company"}).status_code == 200
    r = client.post("/api/demo/reset", headers=o)
    assert r.status_code == 409 and "not part of the demo" in r.json()["error"]["message"]
    with client.app.state.ctx.factory() as s:
        assert s.scalar(select(Source.id).where(Source.name == "Mine")) is not None  # nothing was erased


def test_the_app_refuses_an_example_secret_outside_demo_mode(tmp_path):
    with pytest.raises(ConfigError):
        create_app(real_settings(tmp_path, session_secret="change-me-to-a-long-random-string"))


def test_a_demo_password_next_to_a_real_folder_is_refused(tmp_path):
    with pytest.raises(ConfigError) as e:
        create_app(demo_settings(tmp_path, knowledge_dir=str(tmp_path)))
    assert "KNOWLEDGE_DIR" in str(e.value) and not (tmp_path / "d.sqlite3").exists()  # refused before the database was even opened
    (tmp_path / "ok").mkdir()
    create_app(demo_settings(tmp_path / "ok"))  # a plain demo starts


def test_live_mode_refuses_the_demo_identity_and_lists_it_in_draft_mode(tmp_path):
    with pytest.raises(ConfigError) as e:
        create_app(real_settings(tmp_path, mode="live", company_name="Pinegate Works", email_from="lorefern@example.test"))
    assert "COMPANY_NAME" in str(e.value) and "EMAIL_FROM" in str(e.value)
    draft = real_settings(tmp_path, company_name="Pinegate Works", email_from="lorefern@example.test")
    assert any("COMPANY_NAME" in p for p in draft.problems()) and any("EMAIL_FROM" in p for p in draft.problems())  # listed, but draft mode still starts
    create_app(draft)
    ok = real_settings(tmp_path, mode="live")
    assert ok.runtime_errors() == [] and not [p for p in ok.problems() if "COMPANY_NAME" in p or "EMAIL_FROM" in p]
    assert not any("COMPANY_NAME" in p for p in demo_settings(tmp_path).problems())  # a demo has its own sample company, and that is not a problem


def test_a_bad_time_zone_and_plain_text_mail_are_problems(tmp_path):
    s = real_settings(tmp_path, timezone="Nowhere/City", smtp_host="mail.acme.test", smtp_use_tls=False)
    problems = " ".join(s.problems())
    assert "TIMEZONE" in problems and "SMTP_USE_TLS" in problems
    assert not any("SMTP_USE_TLS" in p for p in real_settings(tmp_path, smtp_host="localhost", smtp_use_tls=False).problems())


def test_today_follows_the_time_zone(tmp_path, monkeypatch):
    from datetime import UTC, datetime

    from lorefern import clock

    app = create_app(real_settings(tmp_path, timezone="Pacific/Auckland"))
    ctx = app.state.ctx
    monkeypatch.setattr(clock, "now", lambda session, demo: datetime(2026, 12, 1, 15, 0, tzinfo=UTC))  # 04:00 the next morning in Auckland
    with ctx.factory() as s:
        assert ctx.today(s).isoformat() == "2026-12-02"
        ctx.settings.timezone = "UTC"
        assert ctx.today(s).isoformat() == "2026-12-01"


def test_an_empty_line_in_the_env_file_means_not_set(tmp_path):
    f = tmp_path / "e.env"
    f.write_text("LLM_CALL_BUDGET=\nLLM_BUDGET_USD=\nLOGIN_BURST=\nSMTP_PORT=\nTIMEZONE=\n")
    s = Settings(_env_file=str(f))
    assert s.llm_call_budget is None and s.login_burst == 5 and s.smtp_port == 587 and s.timezone == "UTC"


def test_secrets_stay_out_of_the_settings_text():
    s = Settings(_env_file=None, notion_token="tok-notion-secret", fireflies_token="tok-fire-secret", fathom_token="tok-fath-secret", smtp_password="pw-smtp-secret")
    text = repr(s) + str(s)
    assert not any(x in text for x in ("tok-notion-secret", "tok-fire-secret", "tok-fath-secret", "pw-smtp-secret"))


def test_the_session_and_the_audience_use_the_same_cleaned_email(tmp_path):
    i = Install(tmp_path)
    r = i.c.post("/api/auth/login", json={"email": "  " + PEOPLE["leadership"].upper(), "password": PASSWORD}).json()
    assert r["role"] == "leadership" and r["user"] == PEOPLE["leadership"]
    me = i.c.get("/api/auth/me", headers={"x-session": r["token"]}).json()
    assert me["audience"] == "leadership" and me["can_write"] is True
