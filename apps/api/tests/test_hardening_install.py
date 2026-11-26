"""A real install does its core job end to end, the settings files are honest and complete, and nothing depends on where the code was installed."""

import io
import json
import re
import shutil
import stat
import subprocess
import zipfile
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from conftest import DATA, make_ctx
from lorefern import world, worker
from lorefern.adapters.smtp import SmtpEmail
from lorefern.api.app import create_app
from lorefern.config import Settings
from lorefern.dburl import resolve_url
from lorefern.models import Document, Meeting, Reminder, Task
from real_install import PASSWORD, PEOPLE, Install, real_settings
from sendora_core.adapters import AdapterError
from sendora_core.safety import DraftModeError, KillSwitchError
from sendora_core.settings import Mode

ROOT = Path(__file__).resolve().parents[3]

COMPANY = {
    "kb/README.md": "---\nvisibility: company\nowner: Grace Lin\n---\n# Company folder\n\nWhat is in this folder.\n",
    "kb/handbook.md": "# Client replies\n\nWe answer every client message within one working day.\n",  # no tag of its own: the README above gives it company
    "kb/finance/README.md": "---\nvisibility: finance\nowner: Grace Lin\n---\n# Finance\n\nFinance material.\n",
    "kb/finance/budget.md": "# Marketing budget\n\nThe marketing budget for the year is 48000 dollars.\n",
    "kb/people/.visibility": "people\n",
    "kb/people/salary.md": "# Pay\n\nPriya earns 98000 dollars a year.\n",
    "meetings/standup.txt": "title: Monday standup\ndate: 2026-12-01\nprovider: file\nvisibility: company\n---\nGrace Lin: Marcus, can you send the client report?\nMarcus Bell: I will send the client report by Friday.\n",
}


def test_a_fresh_real_install_does_its_core_job_end_to_end(tmp_path):
    i = Install(tmp_path, COMPANY, meetings_adapter="file")
    # 1. the owner adds the people who can own work, and the sources: nothing is seeded
    assert i.c.post("/api/owners", headers=i.h["owner"], json={"name": "Marcus Bell", "role": "Delivery"}).status_code == 200
    assert i.c.post("/api/owners", headers=i.h["staff"], json={"name": "Nobody Here"}).status_code == 403
    assert i.get("owner", "/api/documents").json() == [] and i.get("owner", "/api/meetings").json() == []
    kb = i.add_source("Company folder", "kb")
    i.sync(kb)
    # 2. the hourly worker reads the meetings and proposes work, which only a person can approve
    with i.ctx.factory() as s:
        out = world.process_new(s, i.ctx)
        s.commit()
        assert out["proposed_tasks"] >= 1
        assert {t.status for t in s.scalars(select(Task))} == {"proposed"}
        assert i.docs()["handbook.md"]["tag"] == "company" and i.docs()["finance/budget.md"]["tag"] == "finance" and i.docs()["people/salary.md"]["tag"] == "people"
    # 3. a staff member gets a cited answer to a question the company folder covers
    a = i.ask("staff", "How quickly do we answer a client message?")
    assert a["outcome"] == "answer" and "one working day" in a["text"] and a["citations"]
    cited = {c["document_id"] for c in a["citations"]}
    assert all(i.get("staff", f"/api/documents/{d}").status_code == 200 for d in cited)  # every citation opens for the person who got it
    # 4. and none of the restricted facts, in any answer, citation or list, whoever asks the wrong question
    for q in ("What is the marketing budget?", "What does Priya earn?", "How much do we pay Priya a year?"):
        blob = json.dumps(i.ask("staff", q)) + json.dumps(i.ask("leadership", q) if "Priya" in q else "")
        assert "48000" not in blob and "98000" not in blob
    assert "48000" in i.ask("finance", "What is the marketing budget?")["text"]
    assert "98000" in i.ask("owner", "What does Priya earn?")["text"]
    assert "98000" not in i.everything_staff_can_read() and "48000" not in i.everything_staff_can_read()
    # 5. the second person approves, the person who asked cannot, a read only audience cannot
    tid = i.get("leadership", "/api/tasks?status=proposed").json()[0]["id"]
    assert i.c.post(f"/api/tasks/{tid}/approve", headers=i.h["staff"], json={}).status_code == 403
    assert i.c.post(f"/api/tasks/{tid}/approve", headers=i.h["leadership"], json={}).status_code == 200
    # 6. the kill switch set in the app stops changes at once
    assert i.c.post("/api/settings", headers=i.h["owner"], json={"kill_switch": True}).status_code == 200
    assert i.c.post(f"/api/tasks/{tid}/status", headers=i.h["leadership"], json={"status": "done"}).status_code == 409
    assert i.c.get("/api/auth/me", headers=i.h["owner"]).json()["demo_mode"] is False


def test_a_slack_export_folder_and_zip_can_be_imported_and_an_unmapped_channel_is_owner_only(tmp_path):
    def export(root: Path) -> None:
        (root / "general").mkdir(parents=True)
        (root / "hr-private").mkdir()
        (root / "users.json").write_text(json.dumps([{"id": "U1", "name": "ann", "real_name": "Ann Lee"}]))
        (root / "general" / "2026-11-05.json").write_text(json.dumps([{"user": "U1", "text": "Lunch is at noon on Fridays", "ts": "1762300800.0"}]))
        (root / "hr-private" / "2026-11-05.json").write_text(json.dumps([{"user": "U1", "text": "Dana will be let go next week", "ts": "1762300800.0"}]))

    i = Install(tmp_path, {"slack/channels.json": "{}", "slack_channels.json": json.dumps({"general": "company"})})
    export(i.kd / "slack")
    sid = i.add_source("Slack", "slack", kind="slack")
    assert i.sync(sid)["new"] == 2
    tags = {d["title"]: d["tag"] for d in i.get("owner", "/api/documents").json()}
    assert tags == {"#general on 2026-11-05": "company", "#hr-private on 2026-11-05": "people"}  # a channel nobody listed is never company
    assert [d["title"] for d in i.get("staff", "/api/documents").json()] == ["#general on 2026-11-05"]
    with zipfile.ZipFile(i.kd / "export.zip", "w") as zf:
        zf.writestr("users.json", "[]")
        zf.writestr("general/2026-11-06.json", json.dumps([{"user": "U1", "text": "Fresh note", "ts": "1762387200.0"}]))
    zid = i.add_source("Slack zip", "export.zip", kind="slack")
    assert i.sync(zid)["new"] == 1


def test_the_kill_switch_and_draft_mode_set_in_the_app_stop_the_email_even_with_mode_live(tmp_path):
    sent = []

    class Recorder:
        def __init__(self, settings):
            self.settings = settings

        def send(self, *, to, subject, body):
            from sendora_core.safety import guard_write

            guard_write(self.settings, "email.send")  # the adapter's own guard reads the environment settings, which say MODE=live
            sent.append(to)
            return "id"

    i = Install(tmp_path, mode="live", email_adapter="seed")
    i.ctx.adapters.email = Recorder(i.settings)
    from lorefern import reminders
    from lorefern.context import set_state
    from lorefern.models import Owner

    with i.ctx.factory() as s:
        o = Owner(name="Marcus Bell", email="marcus@acme.test", aliases=["Marcus"])
        s.add(o)
        s.flush()
        t = Task(title="Send the report", owner_id=o.id, status="open", tag="company", due_on=date(2026, 12, 2))
        s.add(t)
        s.flush()
        s.add(Reminder(task_id=t.id, kind="overdue", on_date=date(2026, 12, 1), body="Hi Marcus", status="drafted"))
        s.commit()
        rid = s.scalar(select(Reminder.id))
        for key, error in (("kill_switch", KillSwitchError), ("force_draft", DraftModeError)):
            set_state(s, key, "1")
            s.commit()
            with pytest.raises(error):
                reminders.send(s, i.ctx.effective(s), i.ctx.adapters.email, [rid])  # the route passes the settings with the in app switches applied
            assert sent == [] and s.get(Reminder, rid).status == "drafted", key
            set_state(s, key, "0")
            s.commit()
        assert reminders.send(s, i.ctx.effective(s), i.ctx.adapters.email, [rid]) == 1  # both off: the same call sends, so the checks above prove something
    assert sent == ["marcus@acme.test"]


def test_a_reminder_is_sent_once_and_a_failed_batch_does_not_resend_the_first_mails(tmp_path):
    from lorefern import reminders
    from lorefern.models import Owner

    class Flaky:
        def __init__(self):
            self.sent, self.fail_on = [], "b@acme.test"

        def send(self, *, to, subject, body):
            if to == self.fail_on:
                raise AdapterError("down")
            self.sent.append(to)

    i = Install(tmp_path, mode="live")
    mail = Flaky()
    with i.ctx.factory() as s:
        ids = []
        for n, e in enumerate(("a@acme.test", "b@acme.test")):
            o = Owner(name=f"Person {n}", email=e, aliases=[])
            s.add(o)
            s.flush()
            t = Task(title=f"T{n}", owner_id=o.id, status="open", tag="company")
            s.add(t)
            s.flush()
            r = Reminder(task_id=t.id, kind="overdue", on_date=date(2026, 12, 1), body="Hi", status="drafted")
            s.add(r)
            s.flush()
            ids.append(r.id)
        s.commit()
        with pytest.raises(AdapterError):
            reminders.send(s, i.settings, mail, ids)
        assert mail.sent == ["a@acme.test"] and [s.get(Reminder, k).status for k in ids] == ["sent", "drafted"]
        mail.fail_on = ""
        assert reminders.send(s, i.settings, mail, ids) == 1  # only the one that was not sent
        assert mail.sent == ["a@acme.test", "b@acme.test"] and reminders.send(s, i.settings, mail, ids) == 0  # and never twice


# ---- TLS

def test_smtp_checks_the_certificate_and_refuses_plain_text_to_other_machines(monkeypatch):
    calls = {}

    class Fake:
        def __init__(self, host, port, timeout=0):
            calls["host"] = host

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, context=None):
            calls["context"] = context

        def login(self, *a):
            pass

        def noop(self):
            pass

    monkeypatch.setattr("smtplib.SMTP", Fake)
    ok = Settings(_env_file=None, smtp_host="smtp.acme.test", smtp_user="u", smtp_password="p")
    assert SmtpEmail(ok).healthcheck()[0] is True
    assert calls["context"].check_hostname is True and calls["context"].verify_mode.name == "CERT_REQUIRED"
    plain = Settings(_env_file=None, smtp_host="smtp.acme.test", smtp_user="u", smtp_password="p", smtp_use_tls=False)
    calls.clear()
    assert SmtpEmail(plain).healthcheck()[0] is False and calls == {}  # it never even connected
    with pytest.raises(AdapterError):
        SmtpEmail(plain)._smtp()
    local = Settings(_env_file=None, smtp_host="localhost", smtp_user="u", smtp_password="p", smtp_use_tls=False)
    assert SmtpEmail(local).healthcheck()[0] is True and calls["host"] == "localhost"


def test_a_certificate_failure_is_a_plain_message(monkeypatch):
    import ssl

    class Bad:
        def __init__(self, *a, **k):
            pass

        def starttls(self, context=None):
            raise ssl.SSLCertVerificationError("bad cert")

    monkeypatch.setattr("smtplib.SMTP", Bad)
    s = Settings(_env_file=None, mode=Mode.LIVE, demo_mode=False, smtp_host="smtp.acme.test", smtp_user="u", smtp_password="p", email_from="x@acme.test")
    with pytest.raises(AdapterError, match="certificate could not be verified"):
        SmtpEmail(s).send(to="a@acme.test", subject="s", body="b")


# ---- alembic, the worker, the data folder

def test_alembic_reads_the_same_settings_as_the_app(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ENV_FILE", raising=False)
    assert resolve_url("sqlite:///x.db") == "sqlite:///x.db"  # -x url=... wins
    f = tmp_path / "prod.env"
    f.write_text("DATABASE_URL=postgresql+psycopg://u:p@db:5432/lorefern\n")
    assert resolve_url(None, str(f)) == "postgresql+psycopg://u:p@db:5432/lorefern"
    monkeypatch.setenv("ENV_FILE", str(f))
    assert resolve_url() == "postgresql+psycopg://u:p@db:5432/lorefern"
    monkeypatch.setenv("DATABASE_URL", "sqlite:///from-env.db")
    assert resolve_url() == "sqlite:///from-env.db"
    monkeypatch.delenv("DATABASE_URL")
    empty = tmp_path / "empty.env"
    empty.write_text("APP_NAME=x\n")
    with pytest.raises(RuntimeError) as e:
        resolve_url(None, str(empty))
    assert "DATABASE_URL is not set" in str(e.value)


def test_the_alembic_environment_file_uses_the_shared_resolver_and_no_silent_default():
    text = (ROOT / "apps/api/alembic/env.py").read_text()
    assert "resolve_url" in text and "sqlite:///./lorefern.sqlite3" not in text and "os.environ.get" not in text


def test_the_worker_reads_env_file_like_the_api(tmp_path, monkeypatch):
    f = tmp_path / "w.env"
    f.write_text("APP_NAME=from-the-worker-file\nTIMEZONE=Europe/Berlin\n")
    monkeypatch.setenv("ENV_FILE", str(f))
    monkeypatch.delenv("APP_NAME", raising=False)
    monkeypatch.delenv("TIMEZONE", raising=False)
    s = worker.load_settings()
    assert s.app_name == "from-the-worker-file" and s.timezone == "Europe/Berlin"


def test_the_worker_refuses_the_same_unsafe_settings_as_the_api(tmp_path, monkeypatch):
    f = tmp_path / "w.env"
    f.write_text("DEMO_MODE=false\nSESSION_SECRET=change-me-to-a-long-random-string\n")
    monkeypatch.setenv("ENV_FILE", str(f))
    monkeypatch.setattr(worker, "make_engine", lambda *_: pytest.fail("started the database before checking the settings"))
    from sendora_core.settings import ConfigError

    with pytest.raises(ConfigError):
        worker.main()


def installed_like(tmp_path, monkeypatch):
    """What the Docker image looks like: the code is installed, there is no data folder next to it, and SEED_DIR (if set) is the only way to find the demo data."""
    from lorefern.api import app as app_module

    gone = tmp_path / "does-not-exist"
    monkeypatch.setattr(world, "REPO_DATA", gone)
    monkeypatch.setattr(app_module, "REPO_DATA", gone)
    data = tmp_path / "image-data"
    shutil.copytree(Path(DATA) / "seed", data / "seed")
    return data


def demo_app(tmp_path, **kw):
    return create_app(Settings(database_url=f"sqlite:///{tmp_path / 'a.sqlite3'}", session_secret="test-secret-test-secret", _env_file=None, **kw))


def test_the_demo_runs_from_seed_dir_when_the_fallback_folder_is_missing(tmp_path, monkeypatch):
    data = installed_like(tmp_path, monkeypatch)
    app = demo_app(tmp_path, seed_dir=str(data))
    c = TestClient(app, base_url="http://api.test")
    h = {"x-session": c.post("/api/auth/login", json={"email": "owner@example.test", "password": "demo-password-1"}).json()["token"]}
    assert len(c.get("/api/documents", headers=h).json()) > 30  # the world was loaded at start, from SEED_DIR
    assert c.get("/api/company-folder", headers=h).status_code == 200  # the folder page finds the demo folder the same way
    assert c.post("/api/demo/reset", headers=h).status_code == 200
    assert c.post("/api/demo/tick", headers=h).status_code == 200


def test_a_missing_data_folder_is_a_plain_error_and_erases_nothing(tmp_path, monkeypatch):
    data = installed_like(tmp_path, monkeypatch)
    app = demo_app(tmp_path, seed_dir=str(data))
    c = TestClient(app, base_url="http://api.test")
    h = {"x-session": c.post("/api/auth/login", json={"email": "owner@example.test", "password": "demo-password-1"}).json()["token"]}
    before = len(c.get("/api/documents", headers=h).json())
    app.state.ctx.settings.seed_dir = ""  # the folder cannot be found any more
    r = c.post("/api/demo/reset", headers=h)
    assert r.status_code == 503 and "SEED_DIR" in r.json()["error"]["message"]
    assert len(c.get("/api/documents", headers=h).json()) == before  # nothing was erased
    assert c.get("/api/company-folder", headers=h).status_code == 404


def test_the_app_starts_with_demo_mode_and_no_data_folder_at_all(tmp_path, monkeypatch):
    installed_like(tmp_path, monkeypatch)
    app = demo_app(tmp_path)
    assert TestClient(app).get("/health").status_code == 200


def test_no_lookup_resolves_the_data_folder_from_the_installed_package_path():
    """The Docker image runs the code from site-packages or /app, where `parents[N]` of a file can be too short or point at the wrong place."""
    offenders = []
    for p in (ROOT / "apps/api/src/lorefern").rglob("*.py"):
        for n, line in enumerate(p.read_text().splitlines(), 1):
            if "parents[" in line and "REPO_DATA" not in line and "_repo_data" not in line and "try" not in line:
                offenders.append(f"{p.relative_to(ROOT)}:{n}")
    src = (ROOT / "apps/api/src/lorefern/world.py").read_text()
    assert "except IndexError" in src  # the one remaining lookup is guarded
    assert offenders == [] or all("world.py" in o for o in offenders), offenders


# ---- .env.example and the documentation list every setting

def example_names() -> set[str]:
    return set(re.findall(r"^([A-Z][A-Z0-9_]*)=", (ROOT / ".env.example").read_text(), re.M))


def test_env_example_lists_every_setting():
    from sendora_core.settings import BaseAppSettings

    names = {n.upper() for n in Settings.model_fields} | {n.upper() for n in BaseAppSettings.model_fields}
    missing = sorted(names - example_names())
    assert not missing, f"add these to .env.example: {missing}"


def test_the_environment_variables_doc_lists_every_setting():
    from sendora_core.settings import BaseAppSettings

    doc = (ROOT / "docs" / "04-ENVIRONMENT-VARIABLES.md").read_text()
    listed = set(re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", doc))
    names = {n.upper() for n in Settings.model_fields} | {n.upper() for n in BaseAppSettings.model_fields}
    missing = sorted(names - listed)
    assert not missing, f"add these to docs/04-ENVIRONMENT-VARIABLES.md: {missing}"


def test_env_example_loads_as_it_is_and_the_docker_steps_are_in_the_docs():
    s = Settings(_env_file=str(ROOT / ".env.example"))
    assert s.demo_mode is False and s.llm_call_budget is None and s.llm_budget_usd is None and s.company_name == "Pinegate Works"
    assert s.runtime_errors()  # the example secret is refused until it is replaced
    for doc in ("docs/08-DEPLOY-HETZNER.md", "docs/04-ENVIRONMENT-VARIABLES.md"):
        text = (ROOT / doc).read_text()
        for needed in ("DEMO_MODE=false", "SESSION_SECRET", "OWNER_PASSWORD_HASH", "POSTGRES_PASSWORD"):
            assert needed in text, (doc, needed)
    assert "openssl rand -hex 24" in (ROOT / "docs/08-DEPLOY-HETZNER.md").read_text()


# ---- the backup script

def fake_docker(tmp_path, dump: str):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    d = bin_dir / "docker"
    d.write_text("#!/bin/sh\ncase \"$*\" in\n  *pg_dump*) printf '%s' \"$FAKE_DUMP\" ;;\n  *tar*) printf 'tarbytes' ;;\nesac\n")
    d.chmod(d.stat().st_mode | stat.S_IEXEC)
    return bin_dir


def run_backup(tmp_path, dump):
    out = tmp_path / "out"
    env = {"PATH": f"{fake_docker(tmp_path, dump)}:/usr/bin:/bin", "BACKUP_DIR": str(out), "FAKE_DUMP": dump, "HOME": str(tmp_path)}
    r = subprocess.run(["sh", str(ROOT / "deploy" / "hetzner" / "backup.sh")], cwd="/", env=env, capture_output=True, text=True)  # cwd is not the repo, as under cron
    return r, out


def test_backup_works_from_any_folder_and_keeps_the_dump_and_the_knowledge_folder(tmp_path):
    r, out = run_backup(tmp_path, "PGDMPcontent")
    assert r.returncode == 0, r.stderr
    assert [p.read_text() for p in out.glob("lorefern-*.dump")] == ["PGDMPcontent"] and [p.read_text() for p in out.glob("knowledge-*.tar")] == ["tarbytes"]


def test_backup_never_keeps_an_empty_dump(tmp_path):
    r, out = run_backup(tmp_path, "")
    assert r.returncode == 1 and "empty" in r.stderr and list(out.glob("lorefern-*")) == []
