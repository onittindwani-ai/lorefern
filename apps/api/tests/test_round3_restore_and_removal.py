"""Round 3 audit, items 1 and 2: setting a source back to `company` never widens a row that was narrowed since it was restricted, and a meeting the recorder no longer returns leaves
the app, with its transcript, passages, decisions, proposed tasks and the text built from them."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from lorefern import ingest, world
from lorefern.adapters.base import RemoteMeeting, RemoteMeetings
from lorefern.models import Decision, Document, Meeting, Question, Task, WeeklyReview
from real_install import Install

POLICY = "# Pay review\n\nThe salary bands for next year are confidential and set at 90000.\n"
NARROWED = "---\nvisibility: people\n---\n" + POLICY
BODY = "Ann Lee: We decided to move all payroll to the new provider in March.\nBob Ray: I will send the payroll plan to everyone by Friday.\nAnn Lee: Agreed.\n"
LAST_WEEK = (datetime.now(UTC).date() - timedelta(days=7)).isoformat()  # inside the week the weekly review covers
HR = f"title: Termination plan\ndate: {LAST_WEEK}\nvisibility: company\n---\nPriya Nair: We decided that Dana Wright goes on Friday and her severance is 40000 dollars.\nSam Okafor: I will prepare the severance letter by Thursday.\nPriya Nair: Agreed.\n"


def transcript(title: str, vis: str = "company", body: str = BODY) -> str:
    return f"title: {title}\ndate: 2026-11-18\nprovider: file\nvisibility: {vis}\n---\n{body}"


def patch(i: Install, sid: int, **body):
    r = i.c.patch(f"/api/sources/{sid}", headers=i.h["owner"], json=body)
    assert r.status_code == 200, r.text
    return r.json()


def folder_source(i: Install) -> int:
    return i.add_source("KB", "kb", "company", untagged_tag="company")


def staff_paths(i: Install) -> set[str]:
    return set(i.docs("staff"))


# ---- item 1, documents

def test_restoring_a_source_keeps_a_tag_written_in_a_file_while_it_was_restricted(tmp_path):
    i = Install(tmp_path, {"kb/pay.md": POLICY, "kb/open.md": "# Lunch\n\nLunch is served at noon on Fridays.\n"})
    sid = folder_source(i)
    i.sync(sid)
    assert staff_paths(i) == {"pay.md", "open.md"}
    patch(i, sid, default_tag="leadership")
    assert staff_paths(i) == set()
    (i.kd / "kb" / "pay.md").write_text(NARROWED, encoding="utf-8")  # someone narrows the file while the source is restricted
    patch(i, sid, default_tag="company")  # the owner sets the source back before anything read the file again
    i.sync(sid)  # the next read applies the tag the file says
    assert staff_paths(i) == {"open.md"}
    assert i.docs()["pay.md"]["tag"] == "people"


def test_restoring_after_a_read_of_the_narrowed_file_never_opens_it_even_for_a_moment(tmp_path):
    i = Install(tmp_path, {"kb/pay.md": POLICY})
    sid = folder_source(i)
    i.sync(sid)
    patch(i, sid, default_tag="leadership")
    (i.kd / "kb" / "pay.md").write_text(NARROWED, encoding="utf-8")
    i.sync(sid)  # read while restricted: the file says people
    patch(i, sid, default_tag="company")
    assert i.docs()["pay.md"]["tag"] == "people" and staff_paths(i) == set()  # right after the restore, with no read in between
    with i.ctx.factory() as s:
        assert {c.tag for c in s.scalar(select(Document)).chunks} == {"people"}
    i.sync(sid)
    assert i.docs()["pay.md"]["tag"] == "people"  # and the next read does not undo it


def test_a_file_added_while_restricted_gets_its_own_tag_back_and_a_changed_file_is_read_again(tmp_path):
    i = Install(tmp_path, {"kb/a.md": "# A\n\nThe first note says the office opens at nine.\n"})
    sid = folder_source(i)
    i.sync(sid)
    patch(i, sid, default_tag="finance")
    (i.kd / "kb" / "b.md").write_text("# B\n\nThe second note says the kitchen closes at six.\n", encoding="utf-8")
    i.sync(sid)
    assert i.docs()["b.md"]["tag"] == "finance"
    patch(i, sid, default_tag="company")
    assert {k: v["tag"] for k, v in i.docs().items()} == {"a.md": "company", "b.md": "company"}  # b.md says nothing, so in an open source it is company wide again
    (i.kd / "kb" / "a.md").write_text("---\nvisibility: clients\n---\n# A\n\nThe first note says the office opens at nine.\n", encoding="utf-8")
    i.sync(sid)
    assert i.docs()["a.md"]["tag"] == "clients"


def test_a_round_trip_with_no_changes_gives_every_row_its_old_tag(tmp_path):
    files = {"kb/a.md": "---\nvisibility: finance\n---\n# A\n\nBudget text for the finance team.\n", "kb/b.md": "# B\n\nPlain text for everyone.\n"}
    i = Install(tmp_path, files)
    sid = folder_source(i)
    i.sync(sid)
    before = {k: v["tag"] for k, v in i.docs().items()}
    patch(i, sid, default_tag="leadership")
    patch(i, sid, default_tag="company")
    assert {k: v["tag"] for k, v in i.docs().items()} == before


# ---- item 1, meetings

def import_meeting(i: Install, vis: str | None, day: str = "2026-11-10", title: str = "Pay review"):
    body = {"title": title, "held_on": day, "text": BODY, **({"visibility": vis} if vis else {})}
    return i.c.post("/api/meetings", headers=i.h["owner"], json=body)


def meetings_source(i: Install) -> int:
    return next(s["id"] for s in i.get("owner", "/api/sources").json() if s["kind"] == "meetings")


def staff_sees_meeting(i: Install, mid: int) -> bool:
    return i.get("staff", f"/api/meetings/{mid}").status_code == 200


def test_restoring_a_source_does_not_reopen_a_meeting_that_was_imported_again_as_people(tmp_path):
    i = Install(tmp_path, {})
    first = import_meeting(i, "company")
    assert first.status_code == 200, first.text
    mid = first.json()["id"]
    assert staff_sees_meeting(i, mid) and i.get("staff", "/api/tasks").json() and i.get("staff", "/api/decisions").json()
    sid = meetings_source(i)
    patch(i, sid, default_tag="leadership")
    again = import_meeting(i, "people")  # the owner imports the same text again, narrower
    assert again.status_code == 200 and again.json()["tag"] == "people"
    patch(i, sid, default_tag="company")
    assert not staff_sees_meeting(i, mid)  # the transcript stays closed
    assert i.get("staff", "/api/tasks").json() == [] and i.get("staff", "/api/decisions").json() == []
    blob = i.everything_staff_can_read()
    assert "payroll" not in blob.lower()
    with i.ctx.factory() as s:
        assert {t.tag for t in s.scalars(select(Task))} == {"people"} and {d.tag for d in s.scalars(select(Decision))} == {"people"}
        assert {d.tag for d in s.scalars(select(Document))} == {"people"}  # the indexed transcript too


def test_a_review_built_after_the_restore_does_not_hold_the_narrowed_meeting(tmp_path):
    i = Install(tmp_path, {})
    day = (i.ctx.today(i.ctx.factory()) - timedelta(days=7)).isoformat()  # last week, so the review covers it
    mid = import_meeting(i, "company", day=day).json()["id"]
    sid = meetings_source(i)
    patch(i, sid, default_tag="leadership")
    import_meeting(i, "people", day=day)
    patch(i, sid, default_tag="company")
    assert i.c.post("/api/reviews/generate", headers=i.h["owner"], json={"scope": "company"}).status_code == 200
    with i.ctx.factory() as s:
        bodies = " ".join(r.body for r in s.scalars(select(WeeklyReview)))
    assert "Pay review" not in bodies and "payroll" not in bodies.lower()
    assert not staff_sees_meeting(i, mid)


def test_tasks_made_while_a_source_was_restricted_follow_their_meeting_when_it_is_restored(tmp_path):
    i = Install(tmp_path, {"meetings/a.txt": transcript("First")}, meetings_adapter="file")
    with i.ctx.factory() as s:
        world.process_new(s, i.ctx)
        s.commit()
    sid = meetings_source(i)
    patch(i, sid, default_tag="leadership")
    (i.kd / "meetings" / "b.txt").write_text(transcript("Second", body="Cy Dune: We decided to move all lease payments to the new bank in June.\nDee Fox: I will send the lease plan to everyone by Friday.\nCy Dune: Agreed.\n"), encoding="utf-8")
    with i.ctx.factory() as s:
        world.process_new(s, i.ctx)  # a new meeting, read and extracted while the source is restricted
        s.commit()
    with i.ctx.factory() as s:
        second = s.scalar(select(Meeting).where(Meeting.title == "Second"))
        assert second.tag == "leadership" and {t.tag for t in s.scalars(select(Task).where(Task.meeting_id == second.id))} == {"leadership"}
    patch(i, sid, default_tag="company")
    with i.ctx.factory() as s:
        second = s.scalar(select(Meeting).where(Meeting.title == "Second"))
        assert second.tag == "company"
        mine = list(s.scalars(select(Task).where(Task.meeting_id == second.id))) + list(s.scalars(select(Decision).where(Decision.meeting_id == second.id)))
        assert mine and {x.tag for x in mine} == {"company"}


# ---- item 2

def make_hr_install(tmp_path, **kw) -> Install:
    i = Install(tmp_path, {"meetings/hr.txt": HR, "meetings/other.txt": transcript("Other")}, meetings_adapter="file", **kw)
    with i.ctx.factory() as s:
        world.process_new(s, i.ctx)
        s.commit()
    return i


def read_meetings(i: Install) -> dict:
    with i.ctx.factory() as s:
        out = ingest.sync_meetings(s, i.ctx, i.ctx.today(s))
        s.commit()
    return out


def titles(i: Install) -> set[str]:
    with i.ctx.factory() as s:
        return {m.title for m in s.scalars(select(Meeting))}


def test_a_deleted_transcript_leaves_the_index_the_meeting_and_the_answers(tmp_path):
    i = make_hr_install(tmp_path)
    assert i.ask("staff", "What is Dana Wright's severance?")["outcome"] == "answer"
    assert i.c.post("/api/reviews/generate", headers=i.h["owner"], json={"scope": "company"}).status_code == 200
    with i.ctx.factory() as s:
        assert "Termination plan" in " ".join(r.body for r in s.scalars(select(WeeklyReview)))  # the review quotes the meeting, so the check below means something
        hr = s.scalar(select(Meeting).where(Meeting.title == "Termination Plan")) or s.scalar(select(Meeting).where(Meeting.external_id == "hr"))
        assert hr is not None and s.scalar(select(Decision).where(Decision.meeting_id == hr.id)) is not None
    (i.kd / "meetings" / "hr.txt").unlink()
    res = read_meetings(i)
    assert res["removed"] == 1
    with i.ctx.factory() as s:
        assert s.scalar(select(Meeting).where(Meeting.external_id == "hr")) is None
        assert not [d for d in s.scalars(select(Document)) if "severance" in d.text.lower()]
        assert not [t for t in s.scalars(select(Task)) if "severance" in t.title.lower() or "severance" in t.quote.lower()]
        assert not [d for d in s.scalars(select(Decision)) if "severance" in (d.title + d.quote).lower()]
        assert all(q.answer == {} for q in s.scalars(select(Question)))  # stored answers may have quoted it
        assert s.scalar(select(WeeklyReview)) is None  # and so may the review, which the next job builds again without it
    assert i.ask("staff", "What is Dana Wright's severance?")["outcome"] != "answer"
    for path in ("/api/documents", "/api/meetings", "/api/tasks?limit=5000", "/api/decisions", "/api/reviews", "/api/sops", "/api/stuck"):  # not /api/questions: that is the person's own words
        assert "severance" not in i.get("owner", path).text.lower(), path
        assert "severance" not in i.get("staff", path).text.lower(), path
    assert "Other" in titles(i)  # the meeting that is still there stays


def test_deleting_every_transcript_removes_them_all(tmp_path):
    i = make_hr_install(tmp_path)
    for f in ("hr.txt", "other.txt"):
        (i.kd / "meetings" / f).unlink()
    assert read_meetings(i)["removed"] == 0  # an empty read is believed only when the next read says the same (round 4)
    assert read_meetings(i)["removed"] == 2
    assert titles(i) == set()


def test_a_task_a_person_already_approved_stays_but_no_longer_quotes_the_meeting(tmp_path):
    i = make_hr_install(tmp_path)
    with i.ctx.factory() as s:
        hr = s.scalar(select(Meeting).where(Meeting.external_id == "hr"))
        proposed = list(s.scalars(select(Task).where(Task.meeting_id == hr.id)))
        assert len(proposed) >= 1
        keep = proposed[0]
        keep.status = "open"  # approved by a person
        keep_id = keep.id
        s.commit()
    (i.kd / "meetings" / "hr.txt").unlink()
    read_meetings(i)
    with i.ctx.factory() as s:
        t = s.get(Task, keep_id)
        assert t is not None and t.meeting_id is None and t.quote == "" and t.status == "open"
        assert not [x for x in s.scalars(select(Task)) if x.status == "proposed" and "severance" in x.title.lower()]


def test_a_read_that_did_not_see_everything_removes_nothing(tmp_path):
    i = make_hr_install(tmp_path)
    real = i.ctx.adapters.meetings

    class Partial:
        def list_meetings(self):
            return RemoteMeetings([m for m in real.list_meetings() if m.external_id != "hr"], complete=False)

    i.ctx.adapters.meetings = Partial()
    res = read_meetings(i)
    assert res["removed"] == 0 and res.get("incomplete") == 1
    assert len(titles(i)) == 2
    i.ctx.adapters.meetings = type("Plain", (), {"list_meetings": lambda self: [m for m in real.list_meetings() if m.external_id != "hr"]})()  # a plain list says nothing about being complete
    assert read_meetings(i)["removed"] == 0
    assert len(titles(i)) == 2


def test_a_transcript_file_that_cannot_be_read_is_not_a_deleted_meeting(tmp_path):
    i = make_hr_install(tmp_path)
    p = i.kd / "meetings" / "hr.txt"
    other = tmp_path / "elsewhere.txt"
    other.write_text(HR, encoding="utf-8")
    p.unlink()
    p.symlink_to(other)  # the folder reader skips links, so this file is not seen, and that is not the same as gone
    res = read_meetings(i)
    assert res["removed"] == 0 and len(titles(i)) == 2


def test_a_meeting_a_person_pasted_in_is_not_removed_by_a_read_of_the_recorder(tmp_path):
    i = make_hr_install(tmp_path)
    r = i.c.post("/api/meetings", headers=i.h["owner"], json={"title": "Pasted", "held_on": "2026-11-12", "text": BODY, "visibility": "company"})
    assert r.status_code == 200, r.text
    for f in ("hr.txt", "other.txt"):
        (i.kd / "meetings" / f).unlink()
    assert read_meetings(i)["removed"] == 0  # the first empty read waits for the second (round 4)
    assert read_meetings(i)["removed"] == 2
    assert titles(i) == {"Pasted"}


def test_a_meeting_the_recorder_never_returned_in_a_demo_is_not_touched(client):
    from conftest import login

    o = login(client)
    before = client.get("/api/meetings", headers=o).json()
    src = next(s for s in client.get("/api/sources", headers=o).json() if s["kind"] == "meetings")
    assert client.post(f"/api/sources/{src['id']}/sync", headers=o).status_code == 200  # the demo's offline recorder returns nothing, and that is not "everything is gone"
    assert client.get("/api/meetings", headers=o).json() == before


def test_fireflies_says_when_a_page_may_have_more_behind_it():
    import httpx

    from lorefern.adapters.meetings import FirefliesMeetings
    from lorefern.config import Settings

    def serve(n: int):
        def handler(req: httpx.Request) -> httpx.Response:
            rows = [{"id": f"t{k}", "title": "T", "date": "2026-11-01", "sentences": [{"speaker_name": "A", "text": "hello there"}], "summary": {"action_items": ""}, "participants": []} for k in range(n)]
            return httpx.Response(200, json={"data": {"transcripts": rows}})

        return FirefliesMeetings(Settings(_env_file=None, fireflies_token="test-only-token"), client=httpx.Client(transport=httpx.MockTransport(handler), base_url="http://fireflies.test"))

    assert serve(3).list_meetings().complete is True
    assert serve(FirefliesMeetings.LIMIT).list_meetings().complete is False  # a full page may have more behind it


def test_a_restricted_meetings_source_keeps_working_after_a_removal(tmp_path):
    i = make_hr_install(tmp_path)
    sid = meetings_source(i)
    patch(i, sid, default_tag="leadership")
    (i.kd / "meetings" / "hr.txt").unlink()
    assert read_meetings(i)["removed"] == 1
    patch(i, sid, default_tag="company")
    assert titles(i) == {"Other"}


def test_the_remote_meeting_type_defaults_to_incomplete():
    assert RemoteMeetings([RemoteMeeting("a", "t", "2026-01-01", "file", [])]).complete is False
