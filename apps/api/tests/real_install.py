"""A real install for the tests: DEMO_MODE off, an owner password, named people for each audience, a knowledge folder on disk, and an app on a fresh SQLite file.
Nothing here uses a demo shortcut, so what these tests prove is true for an install a company runs."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from lorefern.api.app import create_app
from lorefern.config import Settings
from sendora_core.auth import hash_password

REAL_SECRET = "test-only-Rt7Kq2Vw9Xm4Zc8Lb3Nf6Hy1Js5Dp0Ga2Ue7Tq4Wi9"
PASSWORD = "a-long-test-password-1"
_HASH = hash_password(PASSWORD)
PEOPLE = {"owner": "boss@acme.test", "leadership": "lead@acme.test", "finance": "fin@acme.test", "staff": "staff@acme.test"}


def write_tree(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="")
    return root


def real_settings(tmp_path: Path, knowledge: Path | None = None, **kw) -> Settings:
    members = {PEOPLE[a]: {"audience": a, "password_hash": _HASH} for a in ("leadership", "finance", "staff")}
    base = dict(database_url=f"sqlite:///{tmp_path / 'real.sqlite3'}", demo_mode=False, mode="draft", session_secret=REAL_SECRET, owner_email=PEOPLE["owner"], owner_password_hash=_HASH,
                members_json=json.dumps(members), knowledge_dir=str(knowledge or ""), company_name="Acme Ltd", email_from="lorefern@acme.test", allowed_email_domains="acme.test", login_burst=1000)
    base.update(kw)
    return Settings(_env_file=None, **base)


class Install:
    """The app, a client and sign in helpers for the four audiences."""

    def __init__(self, tmp_path: Path, files: dict[str, str] | None = None, **kw):
        self.kd = write_tree(tmp_path / "kb", files or {})
        self.settings = real_settings(tmp_path, self.kd, **kw)
        self.app = create_app(self.settings)
        self.c = TestClient(self.app, base_url="http://api.test")
        self.ctx = self.app.state.ctx
        self.h = {a: self.sign_in(PEOPLE[a]) for a in PEOPLE}

    def sign_in(self, email: str) -> dict:
        r = self.c.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        assert r.status_code == 200, r.text
        return {"x-session": r.json()["token"], "x-lorefern": "1"}

    def add_source(self, name: str, uri: str = "", tag: str = "company", kind: str = "folder", **extra) -> int:
        r = self.c.post("/api/sources", headers=self.h["owner"], json={"kind": kind, "name": name, "uri": uri, "default_tag": tag, **extra})
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def sync(self, sid: int) -> dict:
        r = self.c.post(f"/api/sources/{sid}/sync", headers=self.h["owner"])
        assert r.status_code == 200, r.text
        return r.json()

    def worker_pass(self) -> None:
        """What the hourly worker does with sources."""
        from lorefern import world

        with self.ctx.factory() as s:
            world._sync_sources(s, self.ctx)
            s.commit()

    def get(self, who: str, path: str):
        return self.c.get(path, headers=self.h[who])

    def ask(self, who: str, question: str) -> dict:
        r = self.c.post("/api/ask", headers=self.h[who], json={"question": question})
        assert r.status_code == 200, r.text
        return r.json()

    def everything_staff_can_read(self) -> str:
        """Every read route a staff member has, as one text, so a test can look for a secret anywhere in it."""
        out = []
        for path in ("/api/documents", "/api/meetings", "/api/tasks?limit=5000", "/api/decisions", "/api/sops", "/api/reviews", "/api/questions", "/api/stuck", "/api/reminders", "/api/sources", "/api/overview"):
            r = self.get("staff", path)
            assert r.status_code == 200, (path, r.text)
            out.append(r.text)
        return "\n".join(out)

    def docs(self, who: str = "owner") -> dict[str, dict]:
        return {d["path"]: d for d in self.get(who, "/api/documents").json()}
