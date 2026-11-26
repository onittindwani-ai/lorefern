"""A restricted document is never returned to a person without the tag: through search, answers, citations, lists, history and direct links, on every path that fills the index
(a manual read, the hourly worker, transcripts, Drive refresh), and the index follows deletions, renames and unsharing."""

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from conftest import DATA, login
from lorefern import ingest, untagged, visibility, world
from lorefern.adapters.sources import DriveSource, NotionSource
from lorefern.config import Settings
from lorefern.models import Chunk, Decision, Document, Meeting, Process, Question, Source, Task, WeeklyReview
from real_install import Install
from mock.source_mocks import DriveMock, NotionMock

SALARY = "Engineers are paid a base of 99111 dollars a year"
LAYOFF = "We will close the Dover office and let 14 people go in March"
HANDBOOK = "---\nvisibility: company\nowner: Grace\n---\n# Leave\n\nEvery person gets 25 days of paid leave a year.\n"
HR_SALARY = f"# Salary bands\n\n{SALARY}.\n"  # no header at all
TRANSCRIPT = f"title: Leadership sync\ndate: 2026-11-18\nprovider: fireflies\nvisibility: leadership\n---\nPriya Nair: {LAYOFF}.\nMarcus Bell: I will send the plan by Friday.\n"
SECRETS = ["99111", "Dover", "14 people"]


def nothing_secret(install: Install, *extra: str) -> None:
    blob = install.everything_staff_can_read()
    for q in ("What are engineers paid?", "What is the salary band?", "Are we closing an office?", "Which office closes and when?", "Who will be let go?"):
        blob += json.dumps(install.ask("staff", q))
    for s in SECRETS + list(extra):
        assert s not in blob, s


# ---- LF-H1: each source reads its own folder

def test_two_folder_sources_keep_their_own_folders_and_tags(tmp_path):
    i = Install(tmp_path, {"handbook/leave.md": HANDBOOK, "hr/salary-bands.md": HR_SALARY, "welcome.md": "---\nvisibility: company\n---\n# Welcome\n\nThe office opens at nine.\n"})
    handbook, hr, rest = i.add_source("Handbook", "handbook"), i.add_source("HR", "hr", "people"), i.add_source("Everything else", "")
    i.worker_pass()  # the hourly job, which used to read the whole knowledge folder into every folder source
    with i.ctx.factory() as s:
        held = {src.name: sorted((d.external_id, d.tag) for d in src.documents) for src in s.scalars(select(Source))}
    assert held["Handbook"] == [("leave.md", "company")]
    assert held["HR"] == [("salary-bands.md", "people")]
    assert held["Everything else"] == [("welcome.md", "company")]  # the folders that have a source of their own are left to it
    nothing_secret(i)
    assert i.get("owner", "/api/documents").status_code == 200 and any("Salary" in d["title"] for d in i.get("owner", "/api/documents").json())
    for sid in (handbook, hr, rest):
        i.sync(sid)  # a manual read says the same
    nothing_secret(i)


def test_a_copy_left_by_the_old_behaviour_is_removed_by_the_next_read(tmp_path):
    i = Install(tmp_path, {"handbook/leave.md": HANDBOOK, "hr/salary-bands.md": HR_SALARY})
    handbook = i.add_source("Handbook", "handbook")
    i.add_source("HR", "hr", "people")
    with i.ctx.factory() as s:  # what the old worker did: the whole folder into the Handbook source, the HR file as a company document
        src = s.get(Source, handbook)
        ingest.ingest_folder(s, src, i.kd)
        doc = s.scalar(select(Document).where(Document.source_id == handbook, Document.external_id == "hr/salary-bands.md"))
        doc.tag = "company"
        for c in doc.chunks:
            c.tag = "company"
        s.commit()
    i.sync(handbook)
    nothing_secret(i)
    with i.ctx.factory() as s:
        assert [d.external_id for d in s.scalars(select(Document).where(Document.source_id == handbook))] == ["leave.md"]


# ---- LF-M1: a missing or unreadable tag is the narrowest tag

def test_a_document_nobody_labelled_is_owner_only_until_the_owner_chooses(tmp_path):
    i = Install(tmp_path, {"notes/plain.md": "# Plain\n\nThe garden gate code is changed every June.\n"})
    sid = i.add_source("Notes", "notes")
    i.sync(sid)
    assert [d["tag"] for d in i.get("owner", "/api/documents").json()] == [visibility.narrowest_tag()] == ["people"]
    assert i.get("staff", "/api/documents").json() == [] and i.get("leadership", "/api/documents").json() == []
    assert "garden gate" not in json.dumps(i.ask("staff", "How often is the garden gate code changed?"))
    r = i.c.patch(f"/api/sources/{sid}", headers=i.h["owner"], json={"untagged_tag": "company"})  # the owner's explicit choice for this source
    assert r.status_code == 200 and r.json()["untagged_tag"] == "company"
    i.sync(sid)
    assert [d["tag"] for d in i.get("staff", "/api/documents").json()] == ["company"]
    assert "June" in i.ask("staff", "How often is the garden gate code changed?")["text"]
    assert i.c.patch(f"/api/sources/{sid}", headers=i.h["staff"], json={"untagged_tag": "company"}).status_code == 403
    assert i.c.patch(f"/api/sources/{sid}", headers=i.h["owner"], json={"untagged_tag": "bogus"}).status_code == 422


def test_the_tag_of_a_folder_applies_to_files_that_carry_none(tmp_path):
    i = Install(tmp_path, {"kb/ops/README.md": "---\nvisibility: clients\n---\n# Ops\n\nHow we work.\n", "kb/ops/checklist.md": "# Checklist\n\nCall the client back within a day.\n",
                           "kb/money/.visibility": "finance\n", "kb/money/budget.txt": "The budget for the year is 12 million.\n", "kb/odd/README.md": "---\nvisibility: bogus\n---\n# Odd\n\nSomething.\n",
                           "kb/odd/thing.md": "# Thing\n\nA thing nobody labelled.\n"})
    i.sync(i.add_source("KB", "kb"))
    tags = {d["path"]: d["tag"] for d in i.get("owner", "/api/documents").json()}
    assert tags["ops/checklist.md"] == "clients" and tags["money/budget.txt"] == "finance" and tags["odd/thing.md"] == "people" and tags["odd/README.md"] == "people"
    seen_by_staff = {d["path"] for d in i.get("staff", "/api/documents").json()}
    assert "ops/checklist.md" in seen_by_staff and not any(p.startswith(("money", "odd")) for p in seen_by_staff)


def test_a_header_written_on_windows_or_exported_with_a_byte_order_mark_is_still_read(tmp_path):
    crlf = "﻿---\r\nvisibility: finance\r\nowner: Grace\r\n---\r\n# Budget\r\n\r\nThe budget is 12 million.\r\n"
    i = Install(tmp_path, {"docs/budget.md": crlf})
    i.sync(i.add_source("Docs", "docs"))
    d = i.get("owner", "/api/documents").json()[0]
    assert d["tag"] == "finance" and d["owner"] == "Grace"
    assert i.get("staff", "/api/documents").json() == []


def test_an_unknown_tag_is_the_narrowest_one_and_the_narrowest_follows_the_map(monkeypatch):
    assert visibility.narrowest_tag() == "people" and visibility.narrowest_tag("leadership") == "leadership" and visibility.narrowest_tag("staff") in {"company", "clients"}
    assert visibility.meet_tag("clients", "finance") == "leadership" and visibility.meet_tag("people", "company") == "people"
    assert visibility.widens("people", "clients") and not visibility.widens("company", "clients")
    # an implementer's own map: leadership sees the people tag, and finance people see only company material, so only the owner sees `finance`
    monkeypatch.setitem(visibility.AUDIENCE_TAGS, "leadership", ("company", "clients", "finance", "leadership", "people"))
    monkeypatch.setitem(visibility.AUDIENCE_TAGS, "finance", ("company",))
    assert visibility.audiences_of("finance") == {"owner", "leadership"} and visibility.narrowest_tag() in {"finance", "people", "leadership"}
    monkeypatch.setitem(visibility.AUDIENCE_TAGS, "leadership", ("company", "clients", "leadership", "people"))
    assert visibility.audiences_of("finance") == {"owner"} and visibility.narrowest_tag() == "finance"  # read from the map, not written into the code


# ---- LF-H2: transcripts keep the visibility they declare

def test_transcripts_under_a_folder_source_never_become_company_documents(tmp_path):
    i = Install(tmp_path, {"meetings/m11-leadership.txt": TRANSCRIPT, "loose/board.txt": TRANSCRIPT.replace("Leadership sync", "Board call"), "loose/crlf.txt": TRANSCRIPT.replace("\n", "\r\n").replace("Leadership sync", "CRLF call"),
                           "guide.md": "---\nvisibility: company\n---\n# Guide\n\nStart here.\n"}, meetings_adapter="file")
    i.sync(i.add_source("Whole folder", ""))  # an empty path reads the whole knowledge folder, the meetings folder included
    with i.ctx.factory() as s:
        docs = {d.external_id: d.tag for d in s.scalars(select(Document))}
    assert "meetings/m11-leadership.txt" not in docs  # the meetings reader owns that folder
    assert docs["loose/board.txt"] == "leadership" and docs["loose/crlf.txt"] == "leadership" and docs["guide.md"] == "company"
    with i.ctx.factory() as s:  # and the meetings reader keeps the header's tag
        from lorefern.models import Meeting as M
        ingest.sync_meetings(s, i.ctx, date(2026, 12, 1))
        s.commit()
        assert {m.tag for m in s.scalars(select(M))} == {"leadership"}
        assert {d.tag for d in s.scalars(select(Document).where(Document.doc_type == "meeting_note"))} == {"leadership"}
    nothing_secret(i)
    assert i.get("leadership", "/api/meetings").json() and i.get("staff", "/api/meetings").json() == []


def test_the_hourly_worker_reads_transcripts_with_their_tag_and_a_recorder_meeting_with_no_tag_is_owner_only(tmp_path):
    i = Install(tmp_path, {"meetings/a.txt": TRANSCRIPT, "meetings/b.txt": "title: Plain\ndate: 2026-11-19\nprovider: file\n---\nAnn Lee: The tea budget is 300 dollars.\n"}, meetings_adapter="file")
    with i.ctx.factory() as s:
        world.process_new(s, i.ctx)
        s.commit()
    tags = {m.title: m.tag for m in i.ctx.factory().__enter__().scalars(select(Meeting))}
    assert tags == {"Leadership sync": "leadership", "Plain": "people"}
    nothing_secret(i, "tea budget")
    with i.ctx.factory() as s:
        src = s.scalar(select(Source).where(Source.kind == "meetings"))
        sid = src.id
    assert i.c.patch(f"/api/sources/{sid}", headers=i.h["owner"], json={"untagged_tag": "company"}).status_code == 200
    with i.ctx.factory() as s:
        ingest.sync_meetings(s, i.ctx, date(2026, 12, 1))
        s.commit()
        assert {m.title: m.tag for m in s.scalars(select(Meeting))}["Plain"] == "company"  # chosen by the owner for this source, on purpose


def test_a_pasted_transcript_without_a_tag_gets_the_narrowest_tag_the_writer_may_see(tmp_path):
    i = Install(tmp_path)
    body = {"title": "Pasted", "held_on": "2026-11-30", "text": "Ann Lee: The plan is secret.\nBob Ray: Agreed, I will write it down.\n"}
    r = i.c.post("/api/meetings", headers=i.h["leadership"], json=body).json()
    assert r["tag"] == "leadership"  # leadership cannot see `people`, so it would have created something it could not open
    r2 = i.c.post("/api/meetings", headers=i.h["owner"], json={**body, "title": "Pasted two"}).json()
    assert r2["tag"] == "people"
    assert i.c.post("/api/meetings", headers=i.h["leadership"], json={**body, "title": "Third", "visibility": "people"}).status_code == 422
    assert i.get("staff", "/api/meetings").json() == []


# ---- LF-M2, LF-M6: the index follows deletions, moves and unsharing

def test_a_deleted_or_renamed_file_leaves_the_index_and_nothing_is_left_pointing_at_it(tmp_path):
    i = Install(tmp_path, {"kb/a.md": "---\nvisibility: company\n---\n# Alpha\n\nThe alpha rule is about parrots.\n", "kb/b.md": "---\nvisibility: company\n---\n# Beta\n\nThe beta rule is about cranes.\n"})
    sid = i.add_source("KB", "kb")
    i.sync(sid)
    with i.ctx.factory() as s:
        a = s.scalar(select(Document).where(Document.external_id == "a.md"))
        s.add(Decision(title="Keep the old rule", meeting_id=None, document_id=a.id, status="confirmed", tag="company"))
        s.add(Process(key="parrots", label="Parrots", sop_id=a.id, coverage="covered", tag="company"))
        s.commit()
    assert "parrots" in json.dumps(i.ask("staff", "What is the alpha rule about?"))
    (i.kd / "kb" / "a.md").unlink()
    (i.kd / "kb" / "b.md").rename(i.kd / "kb" / "b2.md")
    assert i.sync(sid)["removed"] == 2
    with i.ctx.factory() as s:
        assert sorted(d.external_id for d in s.scalars(select(Document))) == ["b2.md"]
        assert s.scalar(select(Decision.document_id)) is None and s.scalar(select(Process.sop_id)) is None
        assert s.scalar(select(Chunk.id).join(Document, Chunk.document_id == Document.id).where(Document.external_id == "a.md")) is None
    assert "parrots" not in json.dumps(i.ask("staff", "What is the alpha rule about?")) and "parrots" not in i.everything_staff_can_read()
    assert i.get("staff", "/api/documents").json()[0]["path"] == "b2.md"


def test_a_read_that_cannot_finish_removes_nothing(tmp_path):
    i = Install(tmp_path, {"kb/a.md": HANDBOOK})
    sid = i.add_source("KB", "kb")
    i.sync(sid)
    (i.kd / "kb" / "a.md").write_bytes(b"\xff\xfe broken")  # still there, but not what it was
    assert i.sync(sid)["removed"] == 0
    import shutil

    shutil.rmtree(i.kd / "kb")  # the folder is gone (an unmounted volume): the read stops with a plain message and keeps the index as it is
    r = i.c.post(f"/api/sources/{sid}/sync", headers=i.h["owner"])
    assert r.status_code == 422 and "Nothing was found" in r.json()["error"]["message"]
    assert len(i.docs()) == 1


def test_hidden_folders_and_the_trash_are_not_indexed(tmp_path):
    i = Install(tmp_path, {"kb/ok.md": HANDBOOK, "kb/.trash/old.md": HANDBOOK.replace("Leave", "Trashed"), "kb/.obsidian/x.md": HANDBOOK.replace("Leave", "Hidden"), "kb/node_modules/p.md": HANDBOOK.replace("Leave", "Pkg")})
    i.sync(i.add_source("KB", "kb"))
    assert list(i.docs()) == ["ok.md"]


def _drive(i: Install, mock: DriveMock):
    i.ctx.settings.knowledge_adapter = "drive"
    i.ctx.adapters.knowledge = DriveSource(Settings(_env_file=None, drive_token=mock.token), client=TestClient(mock.app, base_url="http://drive.test"))


def test_a_drive_refresh_drops_files_that_were_deleted_trashed_or_unshared(tmp_path):
    i = Install(tmp_path)
    d = DriveMock()
    doc = "application/vnd.google-apps.document"
    d.files = {"file-open-01": {"name": "Handbook", "mimeType": doc, "text": "---\nvisibility: company\n---\n# Handbook\n\nWe reply to clients within a day."},
               "file-fin-001": {"name": "Margins", "mimeType": doc, "text": "﻿---\r\nvisibility: finance\r\n---\r\n# Margins\r\n\r\nOur margin on retainers is 41 percent."},
               "file-gone-01": {"name": "Offer", "mimeType": doc, "text": "---\nvisibility: leadership\n---\n# Offer\n\nA buyer offered 2 million for the company."}}
    _drive(i, d)
    sid = i.add_source("Drive", "", "company", kind="drive")
    first = i.sync(sid)
    assert first["new"] == 3 and first["removed"] == 0
    assert {x["title"]: x["tag"] for x in i.get("owner", "/api/documents").json()} == {"Handbook": "company", "Margins": "finance", "Offer": "leadership"}
    assert [x["title"] for x in i.get("staff", "/api/documents").json()] == ["Handbook"] and "buyer" not in i.everything_staff_can_read()
    assert any("trashed = false" in q for q in d.queries)  # a real Drive lists trashed files unless asked not to
    del d.files["file-gone-01"]  # unshared, deleted or moved out of the shared folders
    d.files["file-fin-001"]["trashed"] = True
    again = i.sync(sid)
    assert again["removed"] == 2 and again["same"] == 1
    assert [x["title"] for x in i.get("owner", "/api/documents").json()] == ["Handbook"]
    assert "margin on retainers" not in json.dumps(i.ask("finance", "What is our margin on retainers?")) and "buyer" not in json.dumps(i.ask("leadership", "Did a buyer make an offer?"))


def test_drive_sources_with_their_own_folders_never_share_a_file(tmp_path):
    i = Install(tmp_path)
    d = DriveMock()
    doc = "application/vnd.google-apps.document"
    d.files = {"folder-hr-001": {"name": "HR", "mimeType": "application/vnd.google-apps.folder", "text": "", "parents": ["root-folder-1"]},
               "file-hand-01": {"name": "Handbook", "mimeType": doc, "text": "# Handbook\n\nWe reply to clients within a day.", "parents": ["folder-open-1"]},
               "file-pay-001": {"name": "Pay", "mimeType": doc, "text": f"# Pay\n\n{SALARY}.", "parents": ["folder-hr-001"]},
               "file-sub-001": {"name": "Review", "mimeType": doc, "text": "# Review\n\nA private review note about Dana.", "parents": ["folder-hr-sub"]},
               "folder-hr-sub": {"name": "Sub", "mimeType": "application/vnd.google-apps.folder", "text": "", "parents": ["folder-hr-001"]}}
    _drive(i, d)
    open_id = i.add_source("Open Drive", "", "company", kind="drive", untagged_tag="company")
    hr_id = i.add_source("HR Drive", "folder-hr-001", "people", kind="drive")
    assert i.c.post("/api/sources", headers=i.h["owner"], json={"kind": "drive", "name": "Second open", "uri": "", "default_tag": "company"}).status_code == 409
    assert i.c.post("/api/sources", headers=i.h["owner"], json={"kind": "drive", "name": "Bad ids", "uri": "x' or 1=1 --", "default_tag": "company"}).status_code == 422
    i.sync(open_id)  # reads everything the sign in can reach, HR files included, as company: the order that used to leak
    i.sync(hr_id)  # the source that names its own folders takes its files
    with i.ctx.factory() as s:
        held = {src.name: sorted(x.title for x in src.documents) for src in s.scalars(select(Source))}
        assert {x.tag for x in s.scalars(select(Document).join(Source).where(Source.name == "HR Drive"))} == {"people"}
    assert held == {"Open Drive": ["Handbook"], "HR Drive": ["Pay", "Review"]}  # the sub folder is walked
    i.sync(open_id)
    nothing_secret(i, "private review note")
    with i.ctx.factory() as s:
        assert sorted(x.title for x in s.get(Source, open_id).documents) == ["Handbook"]
    assert any("'folder-hr-001' in parents" in q for q in d.queries)


def test_notion_pages_can_be_limited_to_named_pages(tmp_path):
    n = NotionMock()
    n.pages = {"p-wiki-0001": {"title": "Wiki", "blocks": ["Open wiki text here."]}, "p-hr-000001": {"title": "Pay", "blocks": [SALARY]}, "p-hr-child01": {"title": "Pay detail", "blocks": ["More pay detail."], "parent": "p-hr-000001"}}
    src = NotionSource(Settings(_env_file=None, notion_token=n.token), client=TestClient(n.app, base_url="http://notion.test"))
    assert [x.title for x in src.list_documents(["p-hr-000001"])] == ["Pay", "Pay detail"]
    assert len(src.list_documents()) == 3


def test_a_drive_source_is_not_read_while_another_adapter_is_selected(tmp_path):
    i = Install(tmp_path)  # KNOWLEDGE_ADAPTER is seed, which lists nothing: reading must not wipe a Drive source
    sid = i.add_source("Drive", "", "company", kind="drive")
    with i.ctx.factory() as s:
        ingest.store_document(s, s.get(Source, sid), "f1", ingest.parse_text("a.md", "# A\n\nSome text for the test.\n", "a"))
        s.commit()
    r = i.c.post(f"/api/sources/{sid}/sync", headers=i.h["owner"])
    assert r.status_code == 422 and "KNOWLEDGE_ADAPTER" in r.json()["error"]["message"]
    assert len(i.docs("owner")) == 1


# ---- LF-M8: one bad file does not stop the read

def test_one_file_the_database_refuses_is_counted_and_the_rest_is_stored(tmp_path, monkeypatch):
    i = Install(tmp_path, {"kb/a.md": HANDBOOK, "kb/b.md": HANDBOOK.replace("Leave", "Poison"), "kb/c.md": HANDBOOK.replace("Leave", "Third"), "kb/nul.md": "---\nvisibility: company\n---\n# Nul\n\nA line with a zero\x00 byte inside.\n"})
    real = ingest.store_document

    def flaky(session, source, external_id, parsed, *a, **k):
        if "Poison" in parsed.title:
            session.add(Chunk(document_id=None, tag="company", ordinal=0, text="x", stems="x"))  # a row the database refuses
            session.flush()
        return real(session, source, external_id, parsed, *a, **k)

    monkeypatch.setattr(ingest, "store_document", flaky)
    sid = i.add_source("KB", "kb")
    res = i.sync(sid)
    assert res["failed"] == 1 and res["new"] == 3
    monkeypatch.undo()
    assert sorted(i.docs()) == ["a.md", "c.md", "nul.md"]
    nul = i.get("owner", f"/api/documents/{i.docs()['nul.md']['id']}").json()
    assert "\x00" not in nul["text"]


# ---- LF-M5: a document cannot silence another

def test_replacement_claims_are_checked_and_follow_the_files(tmp_path):
    fm = lambda **k: "---\n" + "".join(f"{a}: {b}\n" for a, b in k.items()) + "---\n# T\n\nThe policy text for the test.\n"  # noqa: E731
    i = Install(tmp_path, {"kb/policy.md": fm(title="Expense policy", owner="Grace", visibility="company"), "kb/attack.md": fm(title="Attack", owner="Mallory", visibility="company", supersedes="Expense policy"),
                           "kb/open.md": fm(title="Board policy", owner="Grace", visibility="company"), "kb/narrow.md": fm(title="Narrow", owner="Grace", visibility="leadership", supersedes="Board policy"),
                           "kb/new.md": fm(title="Expense 2027", owner="Grace", visibility="company", supersedes="Expense policy")})
    sid = i.add_source("KB", "kb")
    i.sync(sid)
    status = lambda: {d["path"]: d["status"] for d in i.get("owner", "/api/documents").json()}  # noqa: E731
    assert status()["policy.md"] == "superseded"  # the same owner says so
    assert status()["open.md"] != "superseded"  # a document fewer people can see cannot take a document everyone reads away from them
    (i.kd / "kb" / "new.md").unlink()  # the replacing file is gone: the replaced one is back, and the attack from another owner never worked
    i.sync(sid)
    assert status()["policy.md"] != "superseded"


# ---- LF-M4: a retag never widens a row and clears what was built from it

def test_a_retag_keeps_stricter_tags_and_clears_text_built_earlier(client):
    o, st = login(client), login(client, "staff@example.test")
    ctx = client.app.state.ctx
    with ctx.factory() as s:
        folder = s.scalar(select(Source).where(Source.kind == "folder"))
        before = {d.id: d.tag for d in s.scalars(select(Document).where(Document.source_id == folder.id))}
        assert {"people", "leadership", "clients"} <= set(before.values())
        assert s.scalars(select(WeeklyReview)).first() is not None
    client.post("/api/ask", headers=st, json={"question": "How many days of leave do I get?"})
    assert client.patch(f"/api/sources/{folder.id}", headers=o, json={"default_tag": "clients"}).status_code == 200
    with ctx.factory() as s:
        after = {d.id: d.tag for d in s.scalars(select(Document).where(Document.source_id == folder.id))}
        for k, was in before.items():
            assert not visibility.widens(was, after[k]), (was, after[k])
        assert {after[k] for k, v in before.items() if v == "people"} == {"people"}  # the old code made these visible to staff
        assert {c.tag for c in s.scalars(select(Chunk).join(Document).where(Document.source_id == folder.id, Document.tag == "people"))} <= {"people"}
        assert s.scalars(select(WeeklyReview)).first() is None and s.scalars(select(Process)).first() is None
    assert client.patch(f"/api/sources/{folder.id}", headers=o, json={"default_tag": "leadership"}).status_code == 200
    with ctx.factory() as s:
        assert all(q.answer == {} for q in s.scalars(select(Question).where(Question.audience == "staff")))  # staff can no longer see this tag
    assert all(d["tag"] != "people" for d in client.get("/api/documents", headers=st).json())
    client.patch(f"/api/sources/{folder.id}", headers=o, json={"default_tag": "company"})
    with ctx.factory() as s:
        assert {d.id: d.tag for d in s.scalars(select(Document).where(Document.source_id == folder.id))} == before  # setting it back restores what each row had
