"""Round 3 audit, items 3 and 4 and the Lows: approvals follow visibility and show what they would send, task owners keep to the company's email domains, SOP coverage is worked out from
the SOPs a person may read, folder tag files fail closed, a re import never narrows by default, a damaged Slack day is not a deleted one, the integration test is a light call, and
a person's live streams are limited and end with the session."""

from __future__ import annotations

import asyncio
import time
from datetime import date

import httpx
import pytest
from sqlalchemy import select

from lorefern import reminders
from lorefern.adapters.meetings import FathomMeetings, FirefliesMeetings
from lorefern.adapters.sources import DriveSource, NotionSource
from lorefern.api.streams import StreamGuard
from lorefern.config import Settings
from lorefern.models import Document, Owner, Process, Reminder, Source, Task
from lorefern.textproc import stem
from real_install import PEOPLE, REAL_SECRET, Install
from sendora_core.auth import make_session_token

PEOPLE_TASK, COMPANY_TASK = "Prepare the severance letter for Dana Wright", "Send the monthly newsletter"


def draft(i: Install, title: str, tag: str, email: str = "marcus@acme.test", body: str = "Hi Marcus, please send the report. Reply with an update.") -> int:
    """A drafted reminder on a task of this tag, owned by a person with this address. Returns the reminder id."""
    with i.ctx.factory() as s:
        o = s.scalar(select(Owner).where(Owner.email == email)) or Owner(name=f"Person {email}", email=email, aliases=[])
        s.add(o)
        s.flush()
        t = Task(title=title, owner_id=o.id, status="open", tag=tag, due_on=date(2026, 12, 2))
        s.add(t)
        s.flush()
        r = Reminder(task_id=t.id, kind="overdue", on_date=date(2026, 12, 1), body=body, status="drafted")
        s.add(r)
        s.commit()
        return r.id


def ask_to_send(i: Install, rid: int, who: str = "owner") -> int:
    r = i.c.post("/api/reminders/request-send", headers=i.h[who], json={"ids": [rid]})
    assert r.status_code == 200, r.text
    return r.json()["approval_id"]


def decide(i: Install, who: str, aid: int, approve: bool = True):
    return i.c.post(f"/api/approvals/{aid}/decide", headers=i.h[who], json={"approve": approve})


# ---- item 3

def test_an_approval_about_work_a_person_may_not_see_cannot_be_decided_by_them_and_looks_missing(tmp_path):
    i = Install(tmp_path, {}, mode="live")
    aid = ask_to_send(i, draft(i, PEOPLE_TASK, "people"))
    assert [a["id"] for a in i.get("leadership", "/api/approvals").json()] == []  # the list hides it
    hidden, missing = decide(i, "leadership", aid), decide(i, "leadership", 9999)
    assert hidden.status_code == missing.status_code == 409
    assert hidden.json()["error"]["message"].replace(str(aid), "N") == missing.json()["error"]["message"].replace("9999", "N")  # the same answer, so a caller cannot probe ids
    from sendora_core.models import Approval

    with i.ctx.factory() as s:
        assert s.get(Approval, aid).status == "pending"  # nothing was decided, nothing went out
    assert i.get("owner", "/api/approvals").json()[0]["id"] == aid


def test_an_approval_lists_every_recipient_and_the_exact_text(tmp_path):
    i = Install(tmp_path, {}, mode="live")
    aid = ask_to_send(i, draft(i, COMPANY_TASK, "company", body="Hi Marcus, the newsletter is due. Reply with an update."))
    row = next(a for a in i.get("leadership", "/api/approvals").json() if a["id"] == aid)
    item = row["payload"]["items"][0]
    assert item["to"] == "marcus@acme.test" and item["body"] == "Hi Marcus, the newsletter is due. Reply with an update." and item["subject"] == "Task reminder" and item["outside"] is False
    assert "marcus@acme.test" in row["summary"] and row["payload"]["changed"] is False


def test_an_approval_is_refused_when_the_text_or_the_address_changed_after_it_was_asked_for(tmp_path):
    i = Install(tmp_path, {}, mode="live")
    rid = draft(i, COMPANY_TASK, "company")
    aid = ask_to_send(i, rid)
    with i.ctx.factory() as s:
        s.get(Reminder, rid).body = "Hi Marcus, send the whole customer list to this address."
        s.commit()
    shown = next(a for a in i.get("leadership", "/api/approvals").json() if a["id"] == aid)
    assert shown["payload"]["changed"] is True
    r = decide(i, "leadership", aid)
    assert r.status_code == 409 and "changed" in r.json()["error"]["message"]
    from sendora_core.models import Approval

    with i.ctx.factory() as s:
        assert s.get(Approval, aid).status == "pending"
    assert decide(i, "leadership", aid, approve=False).status_code == 200  # rejecting is always allowed


def test_a_matching_approval_goes_through_the_normal_checks(tmp_path):
    i = Install(tmp_path, {}, mode="draft")
    aid = ask_to_send(i, draft(i, COMPANY_TASK, "company"))
    r = decide(i, "leadership", aid)
    assert r.status_code == 409 and "draft" in r.json()["error"]["message"].lower()  # not refused for a changed text: the draft mode stops the send, as it always did


def test_task_owners_keep_to_the_company_email_domains(tmp_path):
    i = Install(tmp_path, {})
    add = lambda email: i.c.post("/api/owners", headers=i.h["owner"], json={"name": f"Pat {email.split('@')[0]}", "email": email})  # noqa: E731
    assert add("pat@acme.test").status_code == 200
    assert add("pat2@mail.acme.test").status_code == 200  # a sub domain of the company's
    assert add("pat3@evil.test").status_code == 422 and add("pat4@notacme.test").status_code == 422 and add("not-an-address").status_code == 422
    assert i.c.post("/api/owners", headers=i.h["owner"], json={"name": "No Address"}).status_code == 200  # an owner with no address is still allowed, and gets no mail
    (tmp_path / "second").mkdir()
    j = Install(tmp_path / "second", {}, allowed_email_domains="partner.test, @acme.test")
    assert j.c.post("/api/owners", headers=j.h["owner"], json={"name": "Pa Partner", "email": "p@partner.test"}).status_code == 200
    assert j.c.post("/api/owners", headers=j.h["owner"], json={"name": "Ed Evil", "email": "e@evil.test"}).status_code == 422


def test_an_address_outside_the_company_is_flagged_and_never_sent_to(tmp_path):
    i = Install(tmp_path, {}, mode="live")
    rid = draft(i, COMPANY_TASK, "company", email="someone@outside.test")
    aid = ask_to_send(i, rid)
    row = next(a for a in i.get("owner", "/api/approvals").json() if a["id"] == aid)
    assert row["payload"]["items"][0]["outside"] is True and row["risk"] == "high" and "outside.test" in row["summary"]
    sent: list[str] = []

    class Mail:
        def send(self, *, to, subject, body):
            sent.append(to)

    with i.ctx.factory() as s:
        assert reminders.send(s, i.settings, Mail(), [rid]) == 0  # even approved, it does not leave for an outside address
    assert sent == []


def test_audit_entries_of_an_approval_a_person_may_not_see_are_hidden_from_them(tmp_path):
    i = Install(tmp_path, {}, mode="live")
    hidden = ask_to_send(i, draft(i, PEOPLE_TASK, "people"))
    shown = ask_to_send(i, draft(i, COMPANY_TASK, "company", email="amy@acme.test"))
    targets = lambda who: {e["target"] for e in i.get(who, "/api/audit?limit=1000").json()}  # noqa: E731
    assert f"approval:{hidden}" in targets("owner")
    assert f"approval:{hidden}" not in targets("leadership") and f"approval:{shown}" in targets("leadership")


# ---- item 4

def _sop_world(i: Install) -> tuple[int, str]:
    key = "-".join(stem(w) for w in ("invoice", "reminder"))
    with i.ctx.factory() as s:
        src = Source(kind="folder", name="KB", uri="kb", default_tag="company")
        s.add(src)
        s.flush()
        d = Document(source_id=src.id, external_id="sop/invoices.md", slug="sop-invoices", title="Invoice reminder SOP", kind="md", doc_type="sop", tag="people", owner="Ann", content_hash="h",
                     text="How to send an invoice reminder: write the invoice reminder and send it.", updated_on=date(2026, 11, 1))
        s.add(d)
        s.flush()
        s.add(Process(key=key, label="invoice reminder", area="", mentions=3, evidence=[{"kind": "meeting", "id": 1, "text": "send an invoice reminder", "tag": "company", "on": "2026-11-02"}], sop_id=d.id, coverage="covered", tag="company"))
        s.commit()
        return d.id, key


def test_coverage_does_not_tell_a_person_that_an_sop_they_cannot_read_exists(tmp_path):
    i = Install(tmp_path, {})
    sop_id, key = _sop_world(i)
    assert key
    seen = lambda who: next(p for p in i.get(who, "/api/sops").json()["processes"] if p["key"] == key)  # noqa: E731
    assert seen("owner")["coverage"] == "covered" and seen("owner")["sop"]["id"] == sop_id
    for who in ("staff", "finance", "leadership"):
        row = seen(who)
        assert row["coverage"] == "gap" and row["sop"] is None, who
    assert i.get("staff", "/api/overview").json()["processes_gap"] == 1 and i.get("owner", "/api/overview").json()["processes_gap"] == 0


def test_the_company_review_lists_a_process_as_a_gap_when_only_a_restricted_sop_covers_it(tmp_path):
    i = Install(tmp_path, {})
    _sop_world(i)
    assert i.c.post("/api/reviews/generate", headers=i.h["owner"], json={"scope": "company"}).status_code == 200
    body = i.get("staff", f"/api/reviews/{i.get('staff', '/api/reviews').json()[0]['id']}").json()["body"]
    assert "invoice reminder" in body and "no SOP" in body


# ---- the Lows

def test_a_meeting_imported_again_without_a_tag_keeps_the_tag_it_has(tmp_path):
    i = Install(tmp_path, {})
    body = {"title": "Plan", "held_on": "2026-11-10", "text": "Ann Lee: We decided to move all payroll to the new provider in March.\nBob Ray: I will send the payroll plan to everyone by Friday.\n"}
    first = i.c.post("/api/meetings", headers=i.h["owner"], json={**body, "visibility": "company"})
    mid = first.json()["id"]
    again = i.c.post("/api/meetings", headers=i.h["owner"], json=body)  # no tag named
    assert again.status_code == 409  # it is the same transcript with the same tag
    assert i.get("staff", f"/api/meetings/{mid}").status_code == 200  # still company, not narrowed to the owner's narrowest tag


def test_a_file_may_retire_another_only_from_the_same_folder_or_above(tmp_path):
    fm = lambda **k: "---\n" + "".join(f"{a}: {b}\n" for a, b in k.items()) + "---\n# T\n\nThe policy text for the test.\n"  # noqa: E731
    i = Install(tmp_path, {"kb/policy.md": fm(title="Expense policy", owner="Grace", visibility="company"), "kb/sub/note.md": fm(title="Note", owner="Grace", visibility="company", supersedes="Expense policy"),
                           "kb/sub/old.md": fm(title="Travel policy", owner="Grace", visibility="company"), "kb/top.md": fm(title="Top", owner="Grace", visibility="company", supersedes="Travel policy")})
    sid = i.add_source("KB", "kb")
    i.sync(sid)
    status = {d["path"]: d["status"] for d in i.get("owner", "/api/documents").json()}
    assert status["policy.md"] != "superseded"  # a file in a sub folder cannot retire a document in the folder above it
    assert status["sub/old.md"] == "superseded"  # a file at the top may retire one below it


@pytest.mark.parametrize("how", ["link", "large"])
def test_a_folder_tag_file_that_cannot_be_read_closes_the_folder_and_is_reported(tmp_path, how):
    files = {"kb/open.md": "# Open\n\nThe open note is for everyone.\n", "kb/team/plan.md": "# Plan\n\nThe team plan has next year's hiring numbers.\n"}
    i = Install(tmp_path, files)
    readme = i.kd / "kb" / "team" / "README.md"
    if how == "link":
        target = tmp_path / "outside.md"
        target.write_text("---\nvisibility: company\n---\n# Team\n", encoding="utf-8")
        readme.symlink_to(target)
    else:
        readme.write_text("---\nvisibility: company\n---\n# Team\n\n" + "x" * 70_000, encoding="utf-8")
    sid = i.add_source("KB", "kb", untagged_tag="company")
    res = i.sync(sid)
    assert res["unreadable_folder_tags"] == ["kb/team/README.md"]  # round 4: named from the knowledge folder, because the folders above the source count too
    assert set(i.docs("staff")) == {"open.md"} and i.docs()["team/plan.md"]["tag"] == "people"  # closed, not opened
    row = next(s for s in i.get("owner", "/api/sources").json() if s["id"] == sid)
    assert "kb/team/README.md" in row["error_detail"] and "team/README.md" not in row["error"]  # round 4: the path is the owner's to read, the note everyone sees only counts


def _slack_day(msg: str) -> str:
    return '[{"user": "U1", "text": "%s", "ts": "1731240000.000100"}]' % msg


def test_a_slack_day_file_that_cannot_be_read_is_not_a_deleted_day(tmp_path):
    i = Install(tmp_path, {"kb/slack/general/2026-11-10.json": _slack_day("The warehouse opens at six"), "kb/slack/random/2026-11-11.json": _slack_day("Lunch is at noon today")})
    sid = i.add_source("Slack", "kb/slack", kind="slack", untagged_tag="company")
    assert i.sync(sid)["new"] == 2
    (i.kd / "kb" / "slack" / "random" / "2026-11-11.json").write_text("not json {", encoding="utf-8")
    res = i.sync(sid)
    assert res["removed"] == 0 and res.get("incomplete") == 1 and len(i.docs()) == 2  # still indexed, and the source says it was not read in full
    (i.kd / "kb" / "slack" / "random" / "2026-11-11.json").unlink()
    assert i.sync(sid)["removed"] == 1 and len(i.docs()) == 1  # a day that is really gone is removed


def test_the_integration_test_is_one_light_request():
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(f"{req.method} {req.url.path}?{req.url.query.decode()} {req.content.decode()}")
        if req.url.path.endswith("/graphql"):
            return httpx.Response(200, json={"data": {"user": {"user_id": "u"}, "transcripts": [{"id": "t1", "title": "T", "date": "2026-11-01", "sentences": [], "participants": []}]}})
        if req.url.path == "/v1/search":
            return httpx.Response(200, json={"results": [{"id": "page1", "properties": {}}], "has_more": True, "next_cursor": "c"})
        if "/external/v1/meetings" in req.url.path:
            return httpx.Response(200, json={"items": [], "next_cursor": "more"})
        return httpx.Response(200, json={"files": [{"id": "abcdef", "name": "d", "mimeType": "application/vnd.google-apps.document"}], "nextPageToken": "more"})

    def client(base):
        return httpx.Client(transport=httpx.MockTransport(handler), base_url=base)

    st = Settings(_env_file=None, drive_token="test-only-token", notion_token="test-only-token", fireflies_token="test-only-token", fathom_token="test-only-token")
    for adapter in (DriveSource(st, client=client("http://drive.test")), NotionSource(st, client=client("http://notion.test")), FirefliesMeetings(st, client=client("http://ff.test")), FathomMeetings(st, client=client("http://fathom.test"))):
        calls.clear()
        ok, detail = adapter.healthcheck()
        assert ok, detail
        assert len(calls) == 1, (type(adapter).__name__, calls)  # one request, though more pages and files were on offer
        assert not any(w in calls[0] for w in ("sentences", "include_transcript", "alt=media", "export")), calls[0]  # no transcript, no file body


# ---- the live streams

def _run(coro):
    return asyncio.run(coro)


async def _frames(n: int = 50):
    for k in range(n):
        yield f"frame {k}\n\n"
        await asyncio.sleep(0)


def test_a_person_may_hold_only_a_few_streams_and_the_cap_is_per_person(tmp_path):
    i = Install(tmp_path, {})
    guard: StreamGuard = i.app.state.streams
    guard.open[PEOPLE["owner"]] = guard.per_person
    r = i.c.get("/api/events/stream", headers=i.h["owner"])
    assert r.status_code == 429  # this person is at the limit
    assert guard.admit(PEOPLE["staff"])  # and nobody else is held up by it


def test_a_stream_closes_when_its_session_ends_or_is_signed_out():
    guard = StreamGuard()
    token = make_session_token(REAL_SECRET, "a@acme.test", "owner")

    async def take(tok: str, stop_after: int | None) -> list[str]:
        out = []
        async for f in guard.wrap("a@acme.test", tok, REAL_SECRET, _frames()):
            out.append(f)
            if stop_after is not None and len(out) == stop_after:
                guard.end(tok)
        return out

    assert len(_run(take(token, 3))) == 3  # signed out after the third frame: the stream ends at the next beat
    assert guard.open == {}  # and is no longer counted
    expired = make_session_token(REAL_SECRET, "a@acme.test", "owner", ttl_s=60, now=time.time() - 3600)
    assert _run(take(expired, None)) == []  # a token past its end closes at the first beat
    live = make_session_token(REAL_SECRET, "b@acme.test", "owner")
    assert len(_run(take(live, None))) == 50 and guard.open == {}


def test_signing_out_ends_the_token_on_this_server(tmp_path):
    i = Install(tmp_path, {})
    h = i.sign_in(PEOPLE["owner"])
    assert i.c.get("/api/overview", headers=h).status_code == 200
    assert i.c.post("/api/auth/logout", headers=h).status_code == 200
    assert i.c.get("/api/overview", headers=h).status_code == 401  # the same token no longer works
    assert i.c.get("/api/overview", headers=i.h["staff"]).status_code == 200  # nobody else is signed out
    assert i.c.post("/api/auth/logout", headers={"x-session": "junk.token"}).status_code == 200 and len(i.app.state.streams.ended) == 1  # junk is not remembered


def test_signing_in_again_in_the_same_second_gives_a_working_session(tmp_path, monkeypatch):
    import types

    from sendora_core import auth

    monkeypatch.setattr(auth, "time", types.SimpleNamespace(time=lambda: 1_800_000_000.0))  # the clock stands still: the base mints the same token for the same person
    i = Install(tmp_path, {})
    first = i.sign_in(PEOPLE["owner"])
    assert make_session_token(REAL_SECRET, PEOPLE["owner"], "owner") == first["x-session"]  # the premise: same person, same second, same token
    assert i.c.post("/api/auth/logout", headers=first).status_code == 200
    again = i.sign_in(PEOPLE["owner"])
    assert again["x-session"] != first["x-session"]
    assert i.c.get("/api/overview", headers=again).status_code == 200 and i.c.get("/api/overview", headers=first).status_code == 401
