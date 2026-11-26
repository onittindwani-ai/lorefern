"""Change routes check the tag of the row they change, and a hidden row answers exactly like one that does not exist. Logs, events and settings do not leak either."""

import json

import pytest
from sqlalchemy import select

from conftest import login
from lorefern.models import Decision, Meeting, Task
from sendora_core.models import Event

MINUTES = ("Ann Lee: Let's talk about the layoffs.\nBob Ray: I will send the severance plan to payroll by Friday.\nAnn Lee: We decided to close the Dover office in March because the lease is too high.\n"
           "Bob Ray: Agreed.\n")


@pytest.fixture()
def hidden(client):
    """A people tagged meeting with a proposed task and a proposed decision, and a people tagged task made by hand. Leadership cannot see any of them."""
    o = login(client)
    m = client.post("/api/meetings", headers=o, json={"title": "People review", "held_on": "2026-11-30", "text": MINUTES, "visibility": "people"}).json()
    assert m["tag"] == "people" and m["tasks"] >= 1
    t = client.post("/api/tasks", headers=o, json={"title": "Prepare the secret severance letters", "tag": "people"}).json()["id"]
    with client.app.state.ctx.factory() as s:
        task_id = s.scalar(select(Task.id).where(Task.meeting_id == m["id"]))
        dec_id = s.scalar(select(Decision.id).where(Decision.meeting_id == m["id"]))
    return {"o": o, "lead": login(client, "approver@example.test"), "staff": login(client, "staff@example.test"), "meeting": m["id"], "task": task_id, "hand_task": t, "decision": dec_id}


def same_as_missing(client, h, method, path_hidden, path_missing, **kw):
    a, b = getattr(client, method)(path_hidden, headers=h, **kw), getattr(client, method)(path_missing, headers=h, **kw)
    assert (a.status_code, a.json()) == (b.status_code, b.json()), (path_hidden, a.text, b.text)
    return a.status_code


def test_every_change_route_answers_a_hidden_row_like_a_missing_one(client, hidden):
    lead, t = hidden["lead"], hidden["task"]
    for action, body in (("approve", {}), ("reject", {"reason": "x"}), ("status", {"status": "done"}), ("update", {"note": "hello"}), ("reassign", {"owner_id": None}), ("undo", None)):
        kw = {} if body is None else {"json": body}
        assert same_as_missing(client, lead, "post", f"/api/tasks/{t}/{action}", f"/api/tasks/99999/{action}", **kw) == 404, action
        assert same_as_missing(client, lead, "post", f"/api/tasks/{hidden['hand_task']}/{action}", f"/api/tasks/99999/{action}", **kw) == 404, action
    assert same_as_missing(client, lead, "post", f"/api/decisions/{hidden['decision']}/confirm", "/api/decisions/99999/confirm") == 404
    assert same_as_missing(client, lead, "post", f"/api/decisions/{hidden['decision']}/reject", "/api/decisions/99999/reject") == 404
    assert same_as_missing(client, lead, "post", f"/api/meetings/{hidden['meeting']}/extract", "/api/meetings/99999/extract") == 404
    with client.app.state.ctx.factory() as s:  # nothing was changed behind the 404s
        assert s.get(Task, t).status == "proposed" and s.get(Decision, hidden["decision"]).status == "proposed"


def test_bulk_approve_skips_hidden_tasks_like_missing_ones(client, hidden):
    r = client.post("/api/tasks/bulk-approve", headers=hidden["lead"], json={"ids": [hidden["task"], 99999]}).json()
    assert r == {"approved": [], "skipped": [hidden["task"], 99999]}
    r2 = client.post("/api/tasks/bulk-approve", headers=hidden["o"], json={"ids": [hidden["task"]]}).json()
    assert r2["approved"] == [hidden["task"]]  # the owner can see it, so the owner can approve it


def test_the_owner_can_still_change_what_only_the_owner_sees(client, hidden):
    o = hidden["o"]
    assert client.post(f"/api/decisions/{hidden['decision']}/confirm", headers=o).status_code == 200
    assert client.post(f"/api/tasks/{hidden['hand_task']}/status", headers=o, json={"status": "done"}).status_code == 200
    assert client.post(f"/api/meetings/{hidden['meeting']}/extract", headers=o).status_code == 200


def test_a_writer_cannot_create_a_task_with_a_tag_it_cannot_see(client, hidden):
    r = client.post("/api/tasks", headers=hidden["lead"], json={"title": "Something for people", "tag": "people"})
    assert r.status_code == 422
    assert client.post("/api/tasks", headers=hidden["lead"], json={"title": "Something for leaders", "tag": "leadership"}).status_code == 200


def test_reminders_for_hidden_tasks_cannot_be_requested(client, hidden):
    from lorefern.models import Reminder
    from datetime import date

    with client.app.state.ctx.factory() as s:
        s.add(Reminder(task_id=hidden["task"], kind="overdue", on_date=date(2026, 12, 1), body="Hi, secret", status="drafted"))
        s.commit()
        rid = s.scalar(select(Reminder.id).where(Reminder.task_id == hidden["task"]))
    r = client.post("/api/reminders/request-send", headers=hidden["lead"], json={"ids": [rid]})
    assert r.status_code == 409 and "No drafted reminders" in r.text


def test_the_audit_log_does_not_tell_leadership_about_hidden_rows_or_what_was_typed_on_them(client, hidden):
    o, lead = hidden["o"], hidden["lead"]
    client.post(f"/api/tasks/{hidden['task']}/reject", headers=o, json={"reason": "because of the Dover layoffs"})
    visible = next(x["id"] for x in client.get("/api/tasks?status=proposed&limit=5000", headers=lead).json() if x["tag"] == "company")
    assert client.post(f"/api/tasks/{visible}/approve", headers=o, json={}).status_code == 200
    mine = client.get("/api/audit?limit=500", headers=o).json()
    row = next(e for e in mine if e["action"] == "task.reject")
    assert row["detail"] == {"reason_given": True}  # the words are on the task, not in the log
    theirs = client.get("/api/audit?limit=500", headers=lead).json()
    assert not any(e["target"] in {f"task:{hidden['task']}", f"task:{hidden['hand_task']}", f"meeting:{hidden['meeting']}"} for e in theirs)
    assert "Dover" not in json.dumps(theirs) and "severance" not in json.dumps(theirs)
    assert any(e["target"] == f"task:{visible}" for e in theirs)  # the rest of the log is still there


def test_the_live_event_stream_names_no_meeting_and_counts_nothing(client, hidden):
    client.post(f"/api/meetings/{hidden['meeting']}/extract", headers=hidden["o"])
    with client.app.state.ctx.factory() as s:
        rows = [e for e in s.scalars(select(Event)) if e.kind in {"meeting.extracted", "cycle.ran"}]
        assert rows and all(e.entity_type is None and e.entity_id is None and e.payload == {} for e in rows)


def test_settings_and_integrations_are_for_the_owner_and_leadership(client):
    st, lead = login(client, "staff@example.test"), login(client, "approver@example.test")
    assert client.get("/api/integrations", headers=st).status_code == 403 and client.get("/api/integrations", headers=lead).status_code == 200
    s_staff, s_lead = client.get("/api/settings", headers=st).json(), client.get("/api/settings", headers=lead).json()
    assert s_staff["kill_switch"] in (True, False) and s_staff["problems"] == [] and s_staff["rules"] == {} and "stuck_no_update_days" in s_lead["rules"]


def test_the_company_folder_check_shows_the_stored_tag_and_never_follows_a_link_out_of_the_folder(client, tmp_path):
    from lorefern import folder_tool

    root = tmp_path / "company"
    (root / "01 Company").mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text("---\nvisibility: company\n---\n# Out\n")
    (root / "01 Company" / "README.md").write_text("---\nowner: Ann\nvisibility: company\nreview_by: 2027-01-01\n---\n# R\n\n[a](../../outside.md) [b](../../does-not-exist.md)\n")
    (root / "01 Company" / "link.md").symlink_to(outside)
    (root / "01 Company" / "nolabel.md").write_text("---\nowner: Ann\nreview_by: 2027-01-01\n---\n# Nolabel\n\nNo tag.\n")
    (root / "INDEX.md").write_text("# index\n")
    rep = folder_tool.check(root)
    broken = [f.message for f in rep.findings if f.code == "broken_link"]
    assert len(broken) == 2 and broken[0].replace("outside", "does-not-exist") == broken[1]  # an existing file and a missing one look the same
    assert all("link.md" not in p.name for p in folder_tool.iter_docs(root))  # a link that leaves the folder is not a document
    assert any(f.code == "visibility_missing" and f.path.endswith("nolabel.md") for f in rep.findings)
