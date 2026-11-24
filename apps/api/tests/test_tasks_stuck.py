import json
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from lorefern import stuck, tasks
from lorefern.models import Meeting, Owner, Task, TaskEvent
from conftest import ALL_TAGS

KEY = json.loads((Path(__file__).resolve().parents[3] / "data/seed/stuck_key.json").read_text())
PLANTED = {r["key"]: r for r in json.loads((Path(__file__).resolve().parents[3] / "data/seed/tasks.json").read_text())}


def _find(s, key):
    r = PLANTED[key]
    return s.scalar(select(Task).where(Task.title == r["title"]))


def test_stuck_work_matches_the_hand_written_answer_key_exactly(ro):
    with ro.factory() as s:
        found = {(_find_key(s, x.task_id), x.kind) for x in stuck.detect(s, ro.today(s), ro.settings, ALL_TAGS) if x.task_id}
        want = {tuple(x) for x in KEY["stuck"]}
        assert found == want, (found - want, want - found)
        assert {x.owner for x in stuck.detect(s, ro.today(s), ro.settings, ALL_TAGS) if x.kind == "overloaded"} == set(KEY["overloaded"])


def _find_key(s, task_id):
    t = s.get(Task, task_id)
    return next(k for k, r in PLANTED.items() if r["title"] == t.title)


def test_nothing_done_or_proposed_is_ever_stuck(ro):
    with ro.factory() as s:
        for x in stuck.detect(s, ro.today(s), ro.settings, ALL_TAGS):
            if x.task_id:
                assert s.get(Task, x.task_id).status in ("open", "in_progress", "blocked")


def test_rules_follow_the_settings(ro):
    from lorefern.config import Settings
    with ro.factory() as s:
        strict = Settings(_env_file=None, stuck_no_update_days=2, stuck_blocked_days=1, overload_open_tasks=3)
        loose = Settings(_env_file=None, stuck_no_update_days=60, stuck_blocked_days=60, overload_open_tasks=99, overload_due_soon=99)
        a = stuck.detect(s, ro.today(s), strict, ALL_TAGS)
        b = stuck.detect(s, ro.today(s), loose, ALL_TAGS)
        assert len(a) > len(b)
        assert not any(x.kind in {"no_update", "blocked", "overloaded"} for x in b)


def test_proposals_from_a_meeting_are_proposed_never_open(world):
    with world.factory() as s:
        m12 = s.scalar(select(Meeting).where(Meeting.title == "Weekly operating review", Meeting.held_on == __import__("datetime").date(2026, 11, 23)))
        props = list(s.scalars(select(Task).where(Task.meeting_id == m12.id)))
        assert props and all(t.status == "proposed" for t in props)
        assert all(tasks.validate_quote(m12.transcript.text, t.quote, t.quote_start) for t in props) if hasattr(tasks, "validate_quote") else True


def test_approve_edit_undo_and_audit(world):
    with world.factory() as s:
        t = s.scalar(select(Task).where(Task.status == "proposed"))
        now = world.now(s)
        pid = s.scalar(select(Owner.id).where(Owner.name == "Marcus Bell"))
        tasks.approve(s, t, "priya@x.test", now, owner_id=pid, due_on=now.date() + timedelta(days=3), title="New title")
        assert t.status == "open" and t.owner_id == pid and t.title == "New title"
        with pytest.raises(tasks.TaskError):
            tasks.approve(s, t, "priya@x.test", now)  # cannot approve twice
        tasks.undo_last(s, t, "priya@x.test", now)
        assert t.status == "proposed"
        tasks.reject(s, t, "priya@x.test", now, "duplicate")
        assert t.status == "rejected"
        tasks.undo_last(s, t, "priya@x.test", now)
        assert t.status == "proposed"
        from sendora_core.audit import verify_audit_chain
        assert verify_audit_chain(s)[0]


def test_status_flow_blocked_and_done_and_reopen(world):
    with world.factory() as s:
        t = s.scalar(select(Task).where(Task.status == "open"))
        now = world.now(s)
        tasks.set_status(s, t, "blocked", "x", now, "waiting for access")
        assert t.status == "blocked" and t.blocked_reason == "waiting for access"
        tasks.set_status(s, t, "in_progress", "x", now)
        assert t.blocked_reason == ""
        tasks.set_status(s, t, "done", "x", now)
        assert t.done_at is not None
        with pytest.raises(tasks.TaskError):
            tasks.set_status(s, t, "blocked", "x", now)
        tasks.undo_last(s, t, "x", now)
        assert t.status == "in_progress" and t.done_at is None
        with pytest.raises(tasks.TaskError):
            tasks.add_update(s, s.scalar(select(Task).where(Task.status == "proposed")), "x", now, "hello")


def test_an_update_resets_the_no_update_clock(world):
    with world.factory() as s:
        now = world.now(s)
        t = s.scalar(select(Task).where(Task.title == PLANTED["n01"]["title"]))
        assert any(x.task_id == t.id and x.kind == "no_update" for x in stuck.detect(s, world.today(s), world.settings, ALL_TAGS))
        tasks.add_update(s, t, "ravi", now, "Moved half of the folders")
        assert not any(x.task_id == t.id for x in stuck.detect(s, world.today(s), world.settings, ALL_TAGS))


def test_an_owner_must_exist(world):
    with world.factory() as s:
        t = s.scalar(select(Task).where(Task.status == "proposed"))
        with pytest.raises(tasks.TaskError):
            tasks.approve(s, t, "x", world.now(s), owner_id=99999)
        with pytest.raises(tasks.TaskError):
            tasks.reassign(s, t, 99999, "x", world.now(s))


def test_extraction_twice_adds_nothing_new(world):
    with world.factory() as s:
        m = s.scalar(select(Meeting).where(Meeting.extracted.is_(True)).order_by(Meeting.id.desc()))
        tasks.propose_from_meeting(s, m, world.now(s))
        before = s.query(Task).count()
        again = tasks.propose_from_meeting(s, m, world.now(s))
        assert again["tasks"] == 0 and again["decisions"] == 0 and s.query(Task).count() == before
