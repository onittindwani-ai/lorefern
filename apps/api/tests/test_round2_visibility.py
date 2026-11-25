"""Round 2 audit, F1 to F3: a narrowed transcript takes its tasks, decisions and weekly lines with it; a document never widens its folder; a re-import never widens a meeting."""

import json
from datetime import date
from pathlib import Path

from sqlalchemy import select

from lorefern import ingest, world
from lorefern.models import Decision, Meeting, Source, Task, WeeklyReview
from real_install import Install

BODY = "Ann Lee: We decided to move all payroll to the new provider in March.\nBob Ray: I will send the payroll plan to everyone by Friday.\nAnn Lee: Agreed.\n"


def transcript(vis: str) -> str:
    return f"title: Pay review\ndate: 2026-11-18\nprovider: file\nvisibility: {vis}\n---\n{BODY}"


def read_meetings(i: Install) -> None:
    with i.ctx.factory() as s:
        world.process_new(s, i.ctx)
        s.commit()


def test_narrowing_a_transcript_retags_its_tasks_and_decisions(tmp_path):
    i = Install(tmp_path, {"meetings/pay.txt": transcript("company")}, meetings_adapter="file")
    read_meetings(i)
    assert i.get("staff", "/api/tasks").json() and i.get("staff", "/api/decisions").json()  # the setup really produced rows staff can read
    (i.kd / "meetings/pay.txt").write_text(transcript("people"), encoding="utf-8")
    read_meetings(i)
    blob = i.everything_staff_can_read()
    assert "payroll" not in blob.lower() and "Pay review" not in blob
    assert i.get("staff", "/api/tasks").json() == [] and i.get("staff", "/api/decisions").json() == []
    with i.ctx.factory() as s:
        assert {t.tag for t in s.scalars(select(Task))} == {"people"} and {d.tag for d in s.scalars(select(Decision))} == {"people"}


def test_narrowing_clears_weekly_reviews_and_stored_answers(tmp_path):
    i = Install(tmp_path, {"meetings/pay.txt": transcript("company")}, meetings_adapter="file")
    read_meetings(i)
    with i.ctx.factory() as s:
        s.add(WeeklyReview(week_start=date(2026, 11, 16), scope_tag="company", title="old", body="- payroll move [D1](/decisions?open=1)", sections=[], claims=1, linked=1, generated_at=i.ctx.now(s)))
        s.commit()
    assert i.ask("staff", "When does payroll move to the new provider?")["outcome"] == "answer"
    (i.kd / "meetings/pay.txt").write_text(transcript("people"), encoding="utf-8")
    read_meetings(i)
    with i.ctx.factory() as s:
        assert s.scalars(select(WeeklyReview)).first() is None  # a review that quoted the meeting is cleared, the next job builds it again without it
    assert i.get("staff", "/api/reviews").json() == []


def test_widening_a_transcript_retags_its_tasks_too(tmp_path):
    i = Install(tmp_path, {"meetings/pay.txt": transcript("people")}, meetings_adapter="file")
    read_meetings(i)
    assert i.get("staff", "/api/tasks").json() == []
    (i.kd / "meetings/pay.txt").write_text(transcript("company"), encoding="utf-8")
    read_meetings(i)
    assert i.get("staff", "/api/tasks").json() and i.get("staff", "/api/decisions").json()  # the owner widened it on purpose, so its rows follow


def test_a_meeting_title_is_only_returned_with_a_row_the_person_may_see(tmp_path):
    i = Install(tmp_path, {"meetings/pay.txt": transcript("company")}, meetings_adapter="file")
    read_meetings(i)
    with i.ctx.factory() as s:
        m = s.scalar(select(Meeting))
        for t in s.scalars(select(Task)):
            t.tag = "company"  # a row whose tag lags behind its meeting (data written by an older version)
        for d in s.scalars(select(Decision)):
            d.tag = "company"
        m.tag = "people"
        s.commit()
        tid = s.scalar(select(Task.id))
    assert i.get("staff", f"/api/tasks/{tid}").json()["meeting_title"] == "" and all(d["meeting_title"] == "" for d in i.get("staff", "/api/decisions").json())
    assert i.get("owner", f"/api/tasks/{tid}").json()["meeting_title"] == "Pay review"


def test_the_meeting_route_filters_its_tasks_and_decisions_by_tag(tmp_path):
    i = Install(tmp_path, {"meetings/pay.txt": transcript("company")}, meetings_adapter="file")
    read_meetings(i)
    with i.ctx.factory() as s:
        mid = s.scalar(select(Meeting.id))
        first = s.scalars(select(Task).where(Task.meeting_id == mid)).first()
        first.tag = "people"
        dec = s.scalars(select(Decision).where(Decision.meeting_id == mid)).first()
        dec.tag = "people"
        s.commit()
        hidden_task, hidden_dec = first.title, dec.title
    body = i.get("staff", f"/api/meetings/{mid}").json()
    assert all(t["title"] != hidden_task for t in body["tasks"]) and all(d["title"] != hidden_dec for d in body["decisions"])
    owner = i.get("owner", f"/api/meetings/{mid}").json()
    assert any(t["title"] == hidden_task for t in owner["tasks"])


# ---- F3: a re-import never widens

def post_meeting(i: Install, who: str, **kw):
    body = {"title": "Pay talk", "held_on": "2026-11-18", "text": BODY, **kw}
    return i.c.post("/api/meetings", headers=i.h[who], json=body)


def test_importing_the_same_transcript_again_never_widens_it(tmp_path):
    i = Install(tmp_path)
    first = post_meeting(i, "owner", visibility="people")
    assert first.status_code == 200 and first.json()["tag"] == "people"
    again = post_meeting(i, "leadership", visibility="company")
    assert again.status_code in (404, 409)
    assert i.get("staff", "/api/meetings").json() == [] and i.get("leadership", "/api/meetings").json() == []
    assert i.get("staff", "/api/tasks").json() == []


def test_a_caller_who_cannot_see_the_existing_row_learns_nothing_from_the_answer(tmp_path):
    i = Install(tmp_path)
    post_meeting(i, "owner", visibility="people")
    hidden = post_meeting(i, "leadership", visibility="company")
    assert hidden.status_code == 409 and "Pay talk" not in hidden.text and "2026-11-18" not in hidden.text
    mine = post_meeting(i, "owner", visibility="people")
    assert mine.status_code == 409  # the owner can see it, and it is the same transcript


def test_a_second_import_can_narrow_but_the_rows_follow(tmp_path):
    i = Install(tmp_path)
    first = post_meeting(i, "owner", visibility="company")
    assert first.status_code == 200 and i.get("staff", "/api/tasks").json()
    narrowed = post_meeting(i, "owner", visibility="leadership")
    assert narrowed.status_code == 200 and narrowed.json()["tag"] == "leadership"
    assert i.get("staff", "/api/tasks").json() == [] and i.get("staff", "/api/meetings").json() == []
    wider = post_meeting(i, "owner", visibility="company")
    assert wider.status_code in (404, 409)
    assert i.get("staff", "/api/meetings").json() == []


# ---- F2: the narrowest of document, folder and source wins

DOC = "---\nvisibility: {vis}\nowner: Grace\n---\n# {title}\n\nSalaries are reviewed every January by the board.\n"


def tags_of(i: Install) -> dict[str, str]:
    return {p: d["tag"] for p, d in i.docs().items()}


def test_a_document_cannot_be_wider_than_its_folder(tmp_path):
    i = Install(tmp_path, {"kb/people/.visibility": "people\n", "kb/people/salaries.md": DOC.format(vis="company", title="Salaries"), "kb/people/handbook.md": DOC.format(vis="inherit", title="Handbook"),
                           "kb/people/notes.md": "# Notes\n\nNo header at all, only words about leave.\n", "kb/open/guide.md": DOC.format(vis="company", title="Guide")})
    i.sync(i.add_source("KB", "kb"))
    tags = tags_of(i)
    assert tags["people/salaries.md"] == "people" and tags["people/handbook.md"] == "people" and tags["people/notes.md"] == "people"
    assert tags["open/guide.md"] == "company"
    assert "people/salaries.md" not in i.docs("staff") and "Salaries" not in i.everything_staff_can_read()
    assert "reviewed every January" not in json.dumps(i.ask("staff", "When are salaries reviewed?"))


def test_a_document_may_still_narrow_its_folder(tmp_path):
    i = Install(tmp_path, {"kb/ops/README.md": "---\nvisibility: clients\n---\n# Ops\n\nHow we work.\n", "kb/ops/boardnote.md": DOC.format(vis="leadership", title="Board")})
    i.sync(i.add_source("KB", "kb"))
    tags = tags_of(i)
    assert tags["ops/boardnote.md"] == "leadership" and tags["ops/README.md"] == "clients"


def test_a_nested_folder_can_only_narrow_its_parent(tmp_path):
    i = Install(tmp_path, {"kb/hr/.visibility": "people\n", "kb/hr/policies/README.md": "---\nvisibility: company\n---\n# Policies\n\nAll policies.\n", "kb/hr/policies/leave.md": "# Leave\n\nTwenty five days of leave a year.\n",
                           "kb/fin/README.md": "---\nvisibility: finance\n---\n# Fin\n\nMoney.\n", "kb/fin/team/README.md": "---\nvisibility: leadership\n---\n# Team\n\nWho.\n", "kb/fin/team/x.md": "# X\n\nSome words here for the test.\n"})
    i.sync(i.add_source("KB", "kb"))
    tags = tags_of(i)
    assert tags["hr/policies/leave.md"] == "people" and tags["hr/policies/README.md"] == "people"
    assert tags["fin/team/x.md"] == "leadership"  # finance is read by finance and leadership, leadership by leadership only: the nested folder narrows to leadership


def test_the_folder_checker_warns_about_a_document_wider_than_its_folder(tmp_path):
    from datetime import date

    from lorefern import folder_tool

    out = tmp_path / "f"
    folder_tool.instantiate(Path(__file__).resolve().parents[3] / "templates/company-folder", out, "Acme", "Pat", date(2027, 6, 1))
    wide = (out / "08 People/pay-bands.md")
    wide.write_text("---\ntitle: Pay bands\nowner: Pat\nupdated: 2027-06-01\nreview_by: 2028-01-01\nvisibility: company\ntype: policy\nstatus: current\n---\n\n# Pay bands\n\nBands by level.\n")
    folder_tool.reindex(out, "Acme", date(2027, 6, 1))
    rep = folder_tool.check(out, date(2027, 6, 2))
    warned = [f for f in rep.findings if f.code == "wider_than_folder"]
    assert [f.path for f in warned] == ["08 People/pay-bands.md"] and "people" in warned[0].message and rep.ok


def test_every_shipped_template_takes_the_tag_of_the_folder_it_is_copied_into():
    root = Path(__file__).resolve().parents[3] / "templates/company-folder"
    for f in list(root.glob("11 Templates/*-template.md")) + list(root.rglob("EXAMPLE-*.md")):
        assert "\nvisibility: inherit\n" in f.read_text(), f


def test_a_template_copied_into_the_people_folder_is_people_only(tmp_path):
    from datetime import date
    import shutil

    from lorefern import folder_tool

    root = Path(__file__).resolve().parents[3] / "templates/company-folder"
    out = tmp_path / "kb" / "company"
    folder_tool.instantiate(root, out, "Acme", "Pat", date(2027, 6, 1))
    shutil.copy(out / "11 Templates/sop-template.md", out / "08 People/salary-review.md")
    i = Install(tmp_path)
    i.sync(i.add_source("Company", "company"))
    tags = tags_of(i)
    assert tags["08 People/salary-review.md"] == "people" and tags["11 Templates/sop-template.md"] == "company"
