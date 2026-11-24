"""Defects found by walking the screens as a first time owner (Round 5). Each test fails on the code before its fix."""

import subprocess
import sys
from collections import Counter
from pathlib import Path

from conftest import ROOT, login

IMPORT = "Priya Nair: I will send the board report on Friday.\nLeo Fischer: We decided to move the review to Thursday."


def _owner(client):
    h = login(client)
    assert client.post("/api/demo/reset", headers=h).status_code == 200
    return h


def _sources(client, h):
    return {s["kind"]: s for s in client.get("/api/sources", headers=h).json()}


def _tags(client, h):
    return Counter(d["tag"] for d in client.get("/api/documents?limit=500", headers=h).json())


def test_kill_switch_stops_changes_and_can_be_turned_off(client):
    h = _owner(client)
    task = client.get("/api/tasks?status=proposed", headers=h).json()[0]
    assert client.post("/api/settings", headers=h, json={"kill_switch": True}).json()["kill_switch"] is True
    for path, body in (
        (f"/api/tasks/{task['id']}/approve", {}), ("/api/demo/tick", {}), ("/api/demo/advance", {"hours": 24}), ("/api/decisions/1/confirm", {}),
        ("/api/meetings", {"title": "K", "held_on": "2026-12-01", "text": IMPORT}), ("/api/owners", {"name": "Kay Lee"}),
    ):
        r = client.post(path, headers=h, json=body)
        assert r.status_code == 409 and "kill switch is on" in r.json()["error"]["message"], path
    assert client.patch(f"/api/sources/{_sources(client, h)['folder']['id']}", headers=h, json={"default_tag": "finance"}).status_code == 409
    assert client.post("/api/ask", headers=h, json={"question": "How are databases backed up?"}).json()["outcome"] == "answer"  # reading still works
    assert client.post("/api/settings", headers=h, json={"kill_switch": False}).json()["kill_switch"] is False
    assert client.post(f"/api/tasks/{task['id']}/approve", headers=h, json={}).status_code == 200


def test_the_worker_does_nothing_while_the_kill_switch_is_on(world):
    from lorefern.context import set_state
    from lorefern.worker import run_once
    from sendora_core.jobs import Worker
    from lorefern.jobs import make_handlers
    from sendora_core.models import Job
    from sqlalchemy import select

    with world.factory() as s:
        set_state(s, "kill_switch", "1")
        s.commit()
    assert run_once(world, Worker(world.factory, make_handlers(world))) == 0
    with world.factory() as s:
        assert s.scalars(select(Job)).first() is None


def test_setting_a_source_back_to_company_puts_every_tag_back(client):
    h = _owner(client)
    folder = _sources(client, h)["folder"]
    before = _tags(client, h)
    assert len(before) > 2
    r = client.patch(f"/api/sources/{folder['id']}", headers=h, json={"default_tag": "finance"})
    assert r.status_code == 200 and r.json()["changed"] > 0
    assert _sources(client, h)["folder"]["by_tag"] == {"finance": folder["documents"]}
    assert client.patch(f"/api/sources/{folder['id']}", headers=h, json={"default_tag": "company"}).status_code == 200
    assert _tags(client, h) == before


def test_restricting_the_meetings_source_hides_its_tasks_and_decisions_from_staff(client):
    h = _owner(client)
    staff = login(client, "staff@example.test")
    seen = lambda: (len(client.get("/api/tasks?limit=5000", headers=staff).json()), len(client.get("/api/decisions", headers=staff).json()), len(client.get("/api/meetings", headers=staff).json()))  # noqa: E731
    before = seen()
    meet = _sources(client, h)["meetings"]
    assert client.patch(f"/api/sources/{meet['id']}", headers=h, json={"default_tag": "people"}).status_code == 200
    tasks, decisions, meetings = seen()
    assert meetings == 0 and decisions == 0 and tasks < before[0]
    quoted = [t for t in client.get("/api/tasks?limit=5000", headers=staff).json() if t["meeting_id"]]
    assert quoted == []  # nothing quoting a restricted meeting is left
    assert client.patch(f"/api/sources/{meet['id']}", headers=h, json={"default_tag": "company"}).status_code == 200
    assert seen() == before


def test_the_slack_source_can_be_read_again_and_keeps_its_channel_tags(client):
    h = _owner(client)
    slack = _sources(client, h)["slack"]
    r = client.post(f"/api/sources/{slack['id']}/sync", headers=h)
    assert r.status_code == 200 and r.json()["same"] == slack["documents"]
    assert _sources(client, h)["slack"]["by_tag"] == slack["by_tag"]


def test_a_folder_source_reads_its_own_path_and_refuses_a_bad_one(client):
    h = _owner(client)
    add = lambda **k: client.post("/api/sources", headers=h, json={"kind": "folder", "name": k.pop("name"), "default_tag": "company", **k})  # noqa: E731
    assert add(name="Escape", uri="../elsewhere").status_code == 422
    ok = add(name="Governance only", uri="company/00 Governance")
    assert ok.status_code == 200
    r = client.post(f"/api/sources/{ok.json()['id']}/sync", headers=h)
    assert r.status_code == 200 and 0 < r.json()["new"] < 10  # only that folder, not all 58 files
    missing = add(name="Missing", uri="no-such-folder")
    r = client.post(f"/api/sources/{missing.json()['id']}/sync", headers=h)
    assert r.status_code == 422 and "Nothing was found" in r.json()["error"]["message"]
    assert add(name="governance ONLY").status_code == 409


def test_people_names_are_unique_whatever_the_case_and_need_a_letter(client):
    h = _owner(client)
    assert client.post("/api/owners", headers=h, json={"name": "priya nair"}).status_code == 409
    assert client.post("/api/owners", headers=h, json={"name": "12"}).status_code == 422


def test_an_imported_transcript_is_read_at_once_and_a_repeat_is_refused(client):
    h = _owner(client)
    first = client.post("/api/meetings", headers=h, json={"title": "Board prep", "held_on": "2026-12-01", "text": IMPORT})
    assert first.status_code == 200 and first.json()["tasks"] >= 1
    mine = [t for t in client.get("/api/tasks?status=proposed", headers=h).json() if t["meeting_id"] == first.json()["id"]]
    assert len(mine) == first.json()["tasks"]
    again = client.post("/api/meetings", headers=h, json={"title": "Board prep", "held_on": "2026-12-01", "text": IMPORT})
    assert again.status_code == 409 and "already imported" in again.json()["error"]["message"]
    other = client.post("/api/meetings", headers=h, json={"title": "Board prep", "held_on": "2026-12-01", "text": IMPORT + "\nAisha Khan: I will fix the invoice by Monday."})
    assert other.status_code == 200 and other.json()["id"] != first.json()["id"]  # different words are a different meeting, never a silent overwrite


def test_a_decision_is_decided_once(client):
    h = _owner(client)
    d = client.get("/api/decisions?status=proposed", headers=h).json()[0]
    assert client.post(f"/api/decisions/{d['id']}/confirm", headers=h).status_code == 200
    for verb in ("confirm", "reject"):
        r = client.post(f"/api/decisions/{d['id']}/{verb}", headers=h)
        assert r.status_code == 409 and "Only a proposed decision" in r.json()["error"]["message"]


def test_the_same_reminders_cannot_be_sent_for_approval_twice(client):
    h = _owner(client)
    ids = [r["id"] for r in client.get("/api/reminders", headers=h).json() if r["status"] == "drafted"]
    assert ids
    assert client.post("/api/reminders/request-send", headers=h, json={"ids": ids}).status_code == 200
    again = client.post("/api/reminders/request-send", headers=h, json={"ids": ids})
    assert again.status_code == 409 and "already waiting" in again.json()["error"]["message"]
    assert len([a for a in client.get("/api/approvals", headers=h).json() if a["status"] == "pending"]) == 1


def test_the_folder_check_runs_without_the_web_stack_installed():
    """`python3 tools/check_company_folder.py` is run with whatever python3 the owner has, which may not have the app's libraries."""
    code = ("import sys; sys.modules['sqlalchemy'] = None; sys.path[:0] = [%r, %r]\n"
            "from datetime import date\nfrom lorefern import folder_tool\nfrom pathlib import Path\nrep = folder_tool.check(Path(%r), date(2026, 12, 1))\nprint('ok', len(rep.findings))")
    root = Path(ROOT)
    out = subprocess.run([sys.executable, "-c", code % (str(root / "apps/api/src"), str(root / "packages/core-py/src"), str(root / "templates/company-folder"))], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr[-400:]
    assert out.stdout.startswith("ok")
