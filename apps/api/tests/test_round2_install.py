"""Round 2 audit F6 and F9: the image, the deploy files and the docs say what is true, and the settings object keeps hashes out of its text."""

import os
import stat
import subprocess
from pathlib import Path

from conftest import make_ctx
from lorefern.config import Settings
from real_install import PASSWORD, REAL_SECRET, real_settings
from sendora_core.auth import hash_password

ROOT = Path(__file__).resolve().parents[3]


def test_a_failed_migration_stops_the_api_and_the_health_check_reads_the_database():
    docker = (ROOT / "apps/api/Dockerfile").read_text()
    cmd = next(ln for ln in docker.splitlines() if ln.startswith("CMD "))
    assert cmd.index("set -e") < cmd.index("alembic upgrade head") < cmd.index("uvicorn")  # nothing starts after a failed migration
    health = next(ln for ln in docker.splitlines() if ln.startswith("HEALTHCHECK"))
    assert "/ready" in health and "/health" not in health.replace("/ready", "")
    assert '"healthcheckPath": "/ready"' in (ROOT / "deploy/railway/railway.json").read_text()
    assert "/ready" in (ROOT / "docs/07-DEPLOY-RAILWAY.md").read_text()


def test_the_backup_files_are_private_to_the_user_who_runs_the_backup(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "docker"
    fake.write_text("#!/bin/sh\necho dump-bytes\n")
    fake.chmod(0o755)
    out = tmp_path / "out"
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "BACKUP_DIR": str(out)}
    old = os.umask(0o022)  # a normal umask, which would make the files readable by everyone
    try:
        done = subprocess.run(["sh", str(ROOT / "deploy/hetzner/backup.sh")], env=env, capture_output=True, text=True, timeout=30)
    finally:
        os.umask(old)
    assert done.returncode == 0, done.stderr
    files = list(out.glob("lorefern-*.dump"))
    assert files and stat.S_IMODE(files[0].stat().st_mode) == 0o600 and stat.S_IMODE(out.stat().st_mode) == 0o700


def test_the_caddyfile_publishes_only_the_web_app_unless_the_owner_turns_the_api_on():
    live = [ln for ln in (ROOT / "deploy/hetzner/Caddyfile").read_text().splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    sites = [ln for ln in live if ln.rstrip().endswith("{") and not ln.startswith((" ", "\t"))]
    assert len(sites) == 1 and "8000" not in "\n".join(live)
    assert "one DNS name" in (ROOT / "docs/08-DEPLOY-HETZNER.md").read_text()


def test_the_constraints_header_names_a_way_to_refresh_that_exists():
    head = (ROOT / "constraints.txt").read_text().splitlines()[:4]
    assert not any("make constraints" in ln for ln in head) or "constraints:" in (ROOT / "Makefile").read_text()
    assert "tools/make_constraints.py" in "\n".join(head)


def test_the_docs_describe_self_approval_and_the_model_the_way_the_code_works():
    from sendora_core import approvals

    assert hasattr(approvals, "SelfApprovalError")
    doc = (ROOT / "docs/13-SECURITY-AND-DATA.md").read_text()
    assert "because the base does not do it" not in doc and "SelfApprovalError" in doc
    assert "No language model is called in this release" not in doc and "LLM_BACKEND=offline" in doc


def test_the_answer_writer_default_does_nothing_until_a_model_backend_is_chosen(tmp_path):
    ctx = make_ctx(tmp_path)
    assert ctx.settings.answer_writer == "model" and ctx.model_on() is False
    with ctx.factory() as s:
        assert ctx.answer_writer(s) is None and ctx.proposer(s) is None and ctx.wording(s) is None


def test_hashes_and_the_member_list_never_appear_in_the_text_of_the_settings(tmp_path):
    h = hash_password(PASSWORD)
    s = real_settings(tmp_path, approver_email="lead@acme.test", approver_password_hash=h)
    shown = repr(s) + str(s)
    for secret in (h, s.owner_password_hash, REAL_SECRET, s.members_json):
        assert secret and secret not in shown
    assert s.approver_password_hash == h  # hidden from the text, still there for the app


def test_an_email_the_shared_audit_columns_cannot_hold_is_refused_at_start():
    long_email = "a" * 70 + "@example.com"
    bad = Settings(_env_file=None, owner_email=long_email, session_secret=REAL_SECRET, demo_mode=False, owner_password_hash=hash_password(PASSWORD), company_name="Acme Ltd", email_from="a@acme.test")
    assert any("longer than 80" in e for e in bad.runtime_errors())
    ok = Settings(_env_file=None, owner_email="boss@acme.test", session_secret=REAL_SECRET, demo_mode=False, owner_password_hash=hash_password(PASSWORD), company_name="Acme Ltd", email_from="a@acme.test")
    assert not any("longer than 80" in e for e in ok.runtime_errors())
