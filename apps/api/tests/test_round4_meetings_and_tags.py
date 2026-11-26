"""Round 4 audit: a recorder reply that is not the documented shape is an incomplete read and never deletes meetings, an empty folder or an empty reply needs two reads in a row, a
large drop needs the owner, an unreadable folder is not an empty one, a renamed transcript keeps the confirmed decisions, a transcript header survives a byte order mark, folder tags
count from the knowledge folder, the email allowlist is real, and staff never see a restricted path on the Sources page."""

from __future__ import annotations

import json
import os

import httpx
import pytest
from sqlalchemy import select

from lorefern import ingest, tasks, world
from lorefern.adapters import meetings as meetings_mod
from lorefern.adapters.meetings import FathomMeetings, FileMeetings, FirefliesMeetings, load_transcript_file, visibility_of
from lorefern.config import Settings
from lorefern.models import Decision, Document, Meeting, Source, State, Task
from sendora_core.adapters import AdapterError
from real_install import Install

BODY = "Ann Lee: We decided to move all payroll to the new provider in March.\nBob Ray: I will send the payroll plan to everyone by Friday.\nAnn Lee: Agreed.\n"


def transcript(title: str, vis: str = "company", body: str = BODY) -> str:
    return f"title: {title}\ndate: 2026-11-18\nprovider: file\nvisibility: {vis}\n---\n{body}"


def read(i: Install, **kw) -> dict:
    with i.ctx.factory() as s:
        out = ingest.sync_meetings(s, i.ctx, i.ctx.today(s), **kw)
        s.commit()
    return out


def titles(i: Install) -> set[str]:
    with i.ctx.factory() as s:
        return {m.title for m in s.scalars(select(Meeting))}


def processed(i: Install) -> None:
    with i.ctx.factory() as s:
        world.process_new(s, i.ctx)
        s.commit()


def confirm_all_decisions(i: Install) -> None:
    with i.ctx.factory() as s:
        for d in s.scalars(select(Decision)):
            d.status = "confirmed"
        for t in s.scalars(select(Task)):
            t.status = "open"
        s.commit()


# ---- H1: a reply that is not the documented shape is an incomplete read

GOOD_FF = {"data": {"transcripts": [{"id": "t1", "title": "Pay talk", "date": "2026-11-18", "sentences": [{"speaker_name": "Ann Lee", "text": "We decided to move payroll to the new provider in March."}, {"speaker_name": "Bob Ray", "text": "I will send the payroll plan to everyone by Friday."}], "summary": {"action_items": ""}, "participants": []}]}}


def fireflies(handler) -> FirefliesMeetings:
    return FirefliesMeetings(Settings(_env_file=None, fireflies_token="test-only-token"), client=httpx.Client(transport=httpx.MockTransport(handler), base_url="http://fireflies.test"))


def fathom(handler) -> FathomMeetings:
    return FathomMeetings(Settings(_env_file=None, fathom_token="test-only-token"), client=httpx.Client(transport=httpx.MockTransport(handler), base_url="http://fathom.test"))


BAD_FIREFLIES = [
    {"errors": [{"message": "Too many requests", "code": "too_many_requests"}], "data": None},
    {"errors": [{"message": "oops"}]},
    {"data": None},
    {"data": {"transcripts": None}},
    {"data": {"transcripts": "none"}},
    {"data": {"user": {"user_id": "x"}}},  # a swapped or wrong workspace key
    {},
    [],
    {"data": {"transcripts": ["not an object"]}},
]
BAD_FATHOM = [{}, {"items": None}, {"items": "none"}, {"next_cursor": None}, [], {"items": ["not an object"]}]


@pytest.mark.parametrize("body", BAD_FIREFLIES)
def test_a_fireflies_reply_that_is_not_the_documented_shape_is_an_error_not_an_empty_list(body):
    with pytest.raises(AdapterError):
        fireflies(lambda req: httpx.Response(200, json=body)).list_meetings()


def test_a_fireflies_reply_that_is_not_json_is_an_error():
    with pytest.raises(AdapterError):
        fireflies(lambda req: httpx.Response(200, text="<html>maintenance</html>")).list_meetings()


@pytest.mark.parametrize("body", BAD_FATHOM)
def test_a_fathom_reply_that_is_not_the_documented_shape_is_an_error_not_an_empty_list(body):
    with pytest.raises(AdapterError):
        fathom(lambda req: httpx.Response(200, json=body)).list_meetings()


def test_a_real_empty_account_is_still_an_empty_complete_read():
    assert fireflies(lambda req: httpx.Response(200, json={"data": {"transcripts": []}})).list_meetings().complete is True
    got = fathom(lambda req: httpx.Response(200, json={"items": [], "next_cursor": None})).list_meetings()
    assert list(got) == [] and got.complete is True


@pytest.mark.parametrize("body", [{"errors": [{"message": "Too many requests"}], "data": None}, {"data": {"transcripts": None}}])
def test_a_bad_recorder_reply_never_deletes_the_meetings_decisions_or_tasks(tmp_path, body):
    i = Install(tmp_path, {})
    mode = {"bad": False}
    i.ctx.adapters.meetings = fireflies(lambda req: httpx.Response(200, json=body if mode["bad"] else GOOD_FF))
    assert read(i)["new"] == 1
    with i.ctx.factory() as s:
        for m in s.scalars(select(Meeting)):
            tasks.propose_from_meeting(s, m, i.ctx.now(s))
        s.commit()
    confirm_all_decisions(i)
    with i.ctx.factory() as s:
        before = (len(list(s.scalars(select(Meeting)))), len(list(s.scalars(select(Decision)))), len(list(s.scalars(select(Document)))), len(list(s.scalars(select(Task)))))
    assert before[0] == 1 and before[1] >= 1 and before[3] >= 1
    mode["bad"] = True
    with pytest.raises(AdapterError):
        read(i)
    with i.ctx.factory() as s:
        assert (len(list(s.scalars(select(Meeting)))), len(list(s.scalars(select(Decision)))), len(list(s.scalars(select(Document)))), len(list(s.scalars(select(Task))))) == before


def test_the_hourly_job_survives_a_recorder_that_answers_badly_and_says_so_on_the_source(tmp_path):
    i = Install(tmp_path, {})
    mode = {"bad": False}
    i.ctx.adapters.meetings = fireflies(lambda req: httpx.Response(200, json={"errors": [{"message": "Too many requests"}], "data": None} if mode["bad"] else GOOD_FF))
    processed(i)
    assert titles(i) == {"Pay talk"}
    mode["bad"] = True
    processed(i)  # does not raise, does not remove
    assert titles(i) == {"Pay talk"}
    with i.ctx.factory() as s:
        src = s.scalar(select(Source).where(Source.kind == "meetings"))
        assert src.status == "error" and src.error


# ---- H1: zero returned while meetings exist needs two reads in a row, a large drop needs the owner

def meetings_source_id(i: Install) -> int:
    with i.ctx.factory() as s:
        return s.scalar(select(Source.id).where(Source.kind == "meetings"))


def test_an_empty_read_removes_nothing_until_a_second_read_agrees(tmp_path):
    i = Install(tmp_path, {"meetings/a.txt": transcript("Alpha"), "meetings/b.txt": transcript("Beta")}, meetings_adapter="file")
    processed(i)
    for f in ("a.txt", "b.txt"):
        (i.kd / "meetings" / f).unlink()
    first = read(i)
    assert first["removed"] == 0 and first["removal_pending"] == 2 and titles(i) == {"Alpha", "Beta"}
    second = read(i)
    assert second["removed"] == 2 and titles(i) == set()


def test_a_read_that_finds_a_meeting_again_resets_the_wait(tmp_path):
    i = Install(tmp_path, {"meetings/a.txt": transcript("Alpha")}, meetings_adapter="file")
    processed(i)
    (i.kd / "meetings" / "a.txt").rename(i.kd / "elsewhere.txt")
    assert read(i)["removed"] == 0  # empty once: waiting
    (i.kd / "elsewhere.txt").rename(i.kd / "meetings" / "a.txt")
    assert read(i)["removed"] == 0 and titles(i) == {"Alpha"}  # back again: the wait is over
    (i.kd / "meetings" / "a.txt").rename(i.kd / "elsewhere.txt")
    assert read(i)["removed"] == 0 and titles(i) == {"Alpha"}  # empty again is a first empty read, not a second one
    assert read(i)["removed"] == 1


def test_a_large_drop_is_held_until_the_owner_confirms(tmp_path):
    files = {f"meetings/m{k}.txt": transcript(f"Meeting {k}") for k in range(5)}
    i = Install(tmp_path, files, meetings_adapter="file", meetings_max_removals=2)
    processed(i)
    for k in range(4):
        (i.kd / "meetings" / f"m{k}.txt").unlink()
    res = read(i)
    assert res["removed"] == 0 and res["removal_held"] == 4 and len(titles(i)) == 5
    i.worker_pass()
    processed(i)  # the background job never removes a large drop
    assert len(titles(i)) == 5
    sid = meetings_source_id(i)
    row = next(s for s in i.get("owner", "/api/sources").json() if s["id"] == sid)
    assert row["removals_held"] == 4 and "confirm" in row["error"].lower()
    assert i.c.post(f"/api/sources/{sid}/sync?confirm_removals=true", headers=i.h["leadership"]).status_code == 403  # only the owner confirms
    assert len(titles(i)) == 5
    done = i.c.post(f"/api/sources/{sid}/sync?confirm_removals=true", headers=i.h["owner"])
    assert done.status_code == 200 and done.json()["removed"] == 4 and titles(i) == {"Meeting 4"}
    assert next(s for s in i.get("owner", "/api/sources").json() if s["id"] == sid)["removals_held"] == 0


def test_a_small_drop_still_goes_at_once(tmp_path):
    i = Install(tmp_path, {"meetings/a.txt": transcript("Alpha"), "meetings/b.txt": transcript("Beta")}, meetings_adapter="file")
    processed(i)
    (i.kd / "meetings" / "a.txt").unlink()
    assert read(i)["removed"] == 1 and titles(i) == {"Beta"}


# ---- M1: an unreadable folder is not an empty folder

@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0, reason="a folder with no permissions is still readable by root")
def test_an_unreadable_meetings_folder_is_an_incomplete_read(tmp_path):
    i = Install(tmp_path, {"meetings/pay.txt": transcript("Pay talk")}, meetings_adapter="file")
    processed(i)
    folder = i.kd / "meetings"
    os.chmod(folder, 0o000)
    try:
        assert FileMeetings(i.settings).list_meetings().complete is False
        for _ in range(2):
            res = read(i)
            assert res["removed"] == 0 and res.get("incomplete") == 1
        assert titles(i) == {"Pay talk"}
    finally:
        os.chmod(folder, 0o755)


def test_a_transcript_that_cannot_be_inspected_makes_the_read_incomplete(tmp_path, monkeypatch):
    i = Install(tmp_path, {"meetings/pay.txt": transcript("Pay talk")}, meetings_adapter="file")
    real_stat = type(i.kd).stat

    def failing(self, *a, **kw):
        if self.name == "pay.txt":
            raise PermissionError("no")
        return real_stat(self, *a, **kw)

    monkeypatch.setattr(type(i.kd), "stat", failing)
    got = FileMeetings(i.settings).list_meetings()
    assert got.complete is False and list(got) == []


# ---- M2: a renamed transcript keeps the confirmed decisions

def test_renaming_a_transcript_keeps_the_confirmed_decisions_and_marks_the_source_gone(tmp_path):
    i = Install(tmp_path, {"meetings/pay.txt": transcript("Pay talk")}, meetings_adapter="file")
    processed(i)
    confirm_all_decisions(i)
    assert i.get("staff", "/api/decisions").json()
    (i.kd / "meetings" / "pay.txt").rename(i.kd / "meetings" / "pay-2026.txt")
    assert read(i)["removed"] == 1
    with i.ctx.factory() as s:
        kept = list(s.scalars(select(Decision).where(Decision.status == "confirmed")))
        assert kept and all(d.meeting_id is None and d.quote == "" and d.quote_start == -1 for d in kept)
    rows = i.get("staff", "/api/decisions").json()
    old = [r for r in rows if r["status"] == "confirmed"]
    assert old and all(r["source_gone"] is True and r["meeting_id"] is None for r in old)
    assert "payroll" in old[0]["title"].lower()
    assert i.get("staff", "/api/overview").json()["decisions"] >= 1


def test_a_proposed_decision_still_leaves_with_its_meeting(tmp_path):
    i = Install(tmp_path, {"meetings/pay.txt": transcript("Pay talk"), "meetings/other.txt": transcript("Other")}, meetings_adapter="file")
    processed(i)
    (i.kd / "meetings" / "pay.txt").unlink()
    read(i)
    with i.ctx.factory() as s:
        assert all(d.meeting_id is not None for d in s.scalars(select(Decision)))


# ---- M3: a header that starts with a byte order mark, an indent or Windows line ends

HEADS = {
    "bom_first": ("﻿visibility: people\ntitle: HR one", "people"),
    "bom_title_first": ("﻿title: HR two\nvisibility: people", "people"),
    "indented": ("title: HR three\n   visibility: people", "people"),
    "tabbed_upper": ("title: HR four\n\tVisibility : people", "people"),
    "zero_width": ("title: HR five\n​visibility: people", "people"),
    "later_line": ("title: HR six\ndate: 2026-11-18\nprovider: file\nowner: Ann\nvisibility: people", "people"),
    "plain": ("title: HR seven\nvisibility: leadership", "leadership"),
}


@pytest.mark.parametrize("name", sorted(HEADS))
def test_the_visibility_line_is_found_whatever_the_file_starts_with(tmp_path, name):
    head, want = HEADS[name]
    for nl in ("\n", "\r\n"):
        p = tmp_path / f"{name}{len(nl)}.txt"
        p.write_bytes((head + "\n---\n" + BODY).replace("\n", nl).encode("utf-8"))
        assert visibility_of(p) == want
        m = load_transcript_file(p)
        assert m.lines and m.lines[0][0] == "Ann Lee"  # the body is still found after the header
        assert m.title.startswith("HR")  # and so is the title, even behind a byte order mark


def test_a_people_transcript_with_a_byte_order_mark_never_becomes_company_wide(tmp_path):
    i = Install(tmp_path, {}, meetings_adapter="file")
    for name, (head, _) in HEADS.items():
        p = i.kd / "meetings" / f"{name}.txt"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes((head + "\n---\n" + BODY).encode("utf-8"))
    with i.ctx.factory() as s:
        src = Source(kind="meetings", name="Meeting transcripts", uri="file", default_tag="company", reliability="A", owner="", status="ready")
        s.add(src)
        s.flush()
        from lorefern import untagged

        untagged.put(s, src.id, "company")  # the owner chose company for unlabelled items: a missed tag line would now be company wide
        s.commit()
    read(i)
    with i.ctx.factory() as s:
        tags = {m.title: m.tag for m in s.scalars(select(Meeting))}
    assert tags["HR one"] == "people" and tags["HR two"] == "people" and tags["HR three"] == "people" and tags["HR four"] == "people" and tags["HR five"] == "people"
    assert i.get("staff", "/api/meetings").json() == []


def test_the_header_reader_is_one_function_for_both_readers():
    assert meetings_mod.split_header("﻿title: A\r\nvisibility: people\r\n---\r\nAnn Lee: hello\r\n")[0] == ["title: A", "visibility: people"]


# ---- M4: folder tags count from the knowledge folder, not from the source folder

def test_a_source_inside_a_restricted_folder_keeps_the_ancestors_tag(tmp_path):
    files = {"people/.visibility": "people\n", "people/hr/pay.md": "---\nvisibility: company\n---\n# Pay\n\nSalary bands are confidential and set at 90000.\n",
             "people/hr/deep/more.md": "---\nvisibility: clients\n---\n# More\n\nThe deep note says severance is 40000.\n", "open.md": "---\nvisibility: company\n---\n# Lunch\n\nLunch is at noon on Fridays.\n"}
    i = Install(tmp_path, files)
    sid = i.add_source("HR sub", "people/hr", "company")  # no untagged setting needed
    i.sync(sid)
    docs = i.docs()
    assert docs["pay.md"]["tag"] == "people" and docs["deep/more.md"]["tag"] == "people"
    assert i.docs("staff") == {}
    assert "90000" not in i.everything_staff_can_read()


def test_a_nested_folder_can_still_only_narrow_and_a_source_tag_never_widens(tmp_path):
    files = {"kb/finance/.visibility": "finance\n", "kb/finance/team/.visibility": "company\n", "kb/finance/team/note.md": "# Note\n\nThe team note is about biscuits.\n",
             "kb/finance/team/narrow.md": "---\nvisibility: people\n---\n# Narrow\n\nThe narrow note is about cranes.\n"}
    i = Install(tmp_path, files)
    sid = i.add_source("Finance team", "kb/finance/team", "company", untagged_tag="company")
    i.sync(sid)
    docs = i.docs()
    assert docs["note.md"]["tag"] == "finance" and docs["narrow.md"]["tag"] == "people"  # the ancestor's `finance` is kept, the file's own `people` is narrower
    leadership = {d["path"] for d in i.get("leadership", "/api/documents").json()}
    assert "note.md" in leadership and "narrow.md" not in leadership and "note.md" not in i.docs("staff")


def test_the_knowledge_folder_itself_may_declare_a_tag_for_every_source(tmp_path):
    files = {".visibility": "clients\n", "kb/a.md": "# A\n\nThe alpha note is about parrots.\n"}
    i = Install(tmp_path, files)
    sid = i.add_source("KB", "kb", "company", untagged_tag="company")
    i.sync(sid)
    assert i.docs()["a.md"]["tag"] == "clients"


def test_a_slack_source_inside_a_restricted_folder_keeps_the_ancestors_tag(tmp_path):
    day = "2026-11-02"
    files = {"people/.visibility": "people\n", f"people/slack/general/{day}.json": json.dumps([{"user": "U1", "user_name": "Ann Lee", "text": "Salary review is 90000 for all.", "ts": "1762041600.0"}])}
    i = Install(tmp_path, files)
    sid = i.add_source("Slack", "people/slack", "company", kind="slack", untagged_tag="company")  # the owner chose company for unlabelled days: the folder above must still win
    i.sync(sid)
    assert i.docs("staff") == {}


# ---- M5: the email allowlist

ADDRESSES_THAT_MUST_FAIL = ["a,b@acme.test", "a;b@acme.test", "a b@acme.test", "Ann <ann@acme.test>", "<ann@acme.test>", "ann@acme.test, bob@acme.test", "ann@acme.test;bob@acme.test", "ann\n@acme.test", "ann@acme.test\r\nBcc: x@evil.test", "", "ann", "ann@", "@acme.test", "a@@acme.test", "a..b@acme.test"]


def test_one_address_means_one_address():
    st = Settings(_env_file=None, allowed_email_domains="acme.test,gmail.com", demo_mode=False)
    assert st.email_allowed("ann@acme.test") and st.email_allowed("ann@mail.acme.test")
    for bad in ADDRESSES_THAT_MUST_FAIL + ["a,b@gmail.com", "a;b@gmail.com"]:
        assert not st.email_allowed(bad), bad


def test_a_real_install_needs_the_allowlist_and_sends_nothing_without_it(tmp_path):
    i = Install(tmp_path, {}, allowed_email_domains="")
    assert any("ALLOWED_EMAIL_DOMAINS" in p for p in i.settings.problems())
    assert i.settings.email_domains() == set()
    assert not i.settings.email_allowed("boss@acme.test")  # the owner's own domain is not an allowlist
    r = i.c.post("/api/owners", headers=i.h["owner"], json={"name": "Pat Lee", "email": "pat@acme.test"})
    assert r.status_code == 422 and "ALLOWED_EMAIL_DOMAINS" in r.text
    assert i.c.post("/api/owners", headers=i.h["owner"], json={"name": "No Address"}).status_code == 200
    (tmp_path / "second").mkdir()
    j = Install(tmp_path / "second", {}, allowed_email_domains="acme.test")
    assert not any("ALLOWED_EMAIL_DOMAINS" in p for p in j.settings.problems())
    assert j.c.post("/api/owners", headers=j.h["owner"], json={"name": "Pat Lee", "email": "pat@acme.test"}).status_code == 200


def test_a_free_mail_domain_is_never_the_default_and_a_listed_one_is_a_problem():
    sign_in_on_gmail = Settings(_env_file=None, demo_mode=True, owner_email="boss@gmail.com")
    assert "gmail.com" not in sign_in_on_gmail.email_domains() and not sign_in_on_gmail.email_allowed("anyone@gmail.com")
    listed = Settings(_env_file=None, demo_mode=False, allowed_email_domains="gmail.com")
    assert any("free mail" in p.lower() and "gmail.com" in p for p in listed.problems())
    assert not Settings(_env_file=None, demo_mode=False, allowed_email_domains="acme.test").email_allowed("x@gmail.com")


def test_the_mail_adapter_refuses_a_to_field_that_is_not_one_address():
    from lorefern.adapters.smtp import SmtpEmail

    class Spy(SmtpEmail):
        def _smtp(self):
            raise AssertionError("no connection must be opened for a bad address")

    st = Settings(_env_file=None, smtp_host="mail.acme.test", mode="live", demo_mode=False, email_adapter="smtp")
    for bad in ("a,b@acme.test", "a b@acme.test", "ann@acme.test;bob@acme.test", "Ann <ann@acme.test>", "ann@acme.test\r\nBcc: x@evil.test"):
        with pytest.raises(AdapterError):
            Spy(st).send(to=bad, subject="s", body="b")


# ---- M7: the Sources page shows paths to the owner only

def test_staff_see_a_count_and_the_owner_sees_the_restricted_path(tmp_path):
    files = {"kb/open.md": "# Lunch\n\nLunch is at noon on Fridays.\n", "kb/hr-terminations-2026/x.md": "# X\n\nSecret.\n"}
    i = Install(tmp_path, files)
    (i.kd / "kb" / "hr-terminations-2026" / "README.md").write_text("---\nvisibility: people\n---\n" + "x" * 70000, encoding="utf-8")  # over 64 KB
    sid = i.add_source("KB", "kb", "company", untagged_tag="company")
    i.sync(sid)
    for who in ("staff", "finance", "leadership"):
        text = i.get(who, "/api/sources").text
        assert "hr-terminations-2026" not in text, who
        row = next(s for s in i.get(who, "/api/sources").json() if s["id"] == sid)
        assert "1 folder tag file" in row["error"] and not row.get("error_detail")
    assert "hr-terminations-2026" not in i.everything_staff_can_read()
    owner = next(s for s in i.get("owner", "/api/sources").json() if s["id"] == sid)
    assert "hr-terminations-2026/README.md" in owner["error_detail"]
    assert "hr-terminations-2026" not in json.dumps(owner["error"])


# ---- a typo in a tag is never ignored

def test_a_misspelt_tag_in_a_restricted_source_fails_closed_and_is_counted(tmp_path):
    files = {"kb/typo.md": "---\nvisibility: peple\n---\n# Typo\n\nThe typo note is about owls.\n", "kb/fine.md": "---\nvisibility: finance\n---\n# Fine\n\nThe fine note is about swans.\n"}
    i = Install(tmp_path, files)
    sid = i.add_source("KB", "kb", "leadership")
    res = i.sync(sid)
    docs = i.docs()
    assert docs["typo.md"]["tag"] == "people" and docs["fine.md"]["tag"] == "leadership"  # a tag nobody recognises is owner only, not the source's wider tag; a real one can only narrow
    assert res["unknown_tags"] == 1
    row = next(s for s in i.get("staff", "/api/sources").json() if s["id"] == sid) if i.get("staff", "/api/sources").json() else None
    assert row is None or "typo.md" not in json.dumps(row)


def test_the_updating_guide_names_env_file():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[3] / "docs" / "12-UPDATING.md").read_text(encoding="utf-8")
    assert "ENV_FILE" in text


def test_the_state_rows_for_a_wait_are_small(tmp_path):
    i = Install(tmp_path, {"meetings/a.txt": transcript("Alpha")}, meetings_adapter="file")
    processed(i)
    (i.kd / "meetings" / "a.txt").unlink()
    read(i)
    with i.ctx.factory() as s:
        assert all(len(k) <= 80 for k in s.scalars(select(State.key)))


# ---- a read that did not see everything breaks a streak of empty reads

def test_an_incomplete_read_between_two_empty_reads_breaks_the_streak(tmp_path):
    from lorefern.adapters.base import RemoteMeetings

    i = Install(tmp_path, {"meetings/a.txt": transcript("Alpha")}, meetings_adapter="file")
    processed(i)
    real = i.ctx.adapters.meetings
    (i.kd / "meetings" / "a.txt").rename(i.kd / "elsewhere.txt")
    assert read(i)["removed"] == 0  # empty once
    i.ctx.adapters.meetings = type("Down", (), {"list_meetings": lambda self: RemoteMeetings([], complete=False)})()
    assert read(i)["removed"] == 0  # a read that saw nothing says nothing
    i.ctx.adapters.meetings = real
    assert read(i)["removed"] == 0 and titles(i) == {"Alpha"}  # so this is a first empty read again
    assert read(i)["removed"] == 1


# ---- a zero width character in front of a header does not hide it

@pytest.mark.parametrize("lead", ["﻿", "​", "﻿​", "⁠"])
def test_a_document_that_starts_with_a_zero_width_character_keeps_its_header(tmp_path, lead):
    i = Install(tmp_path, {"kb/hr.md": lead + "---\nvisibility: people\n---\n# Pay\n\nSalary bands are set at 90000.\n"})
    sid = i.add_source("KB", "kb", "company", untagged_tag="company")  # the owner chose company for documents with no tag
    i.sync(sid)
    assert i.docs()["hr.md"]["tag"] == "people" and i.docs("staff") == {}
