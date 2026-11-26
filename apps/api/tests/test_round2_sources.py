"""Round 2 audit F4: a Drive or Notion read that stopped early, or could not read a file, never removes anything from the index, and a file is size checked while it is read."""

import httpx
from sqlalchemy import select

from lorefern import ingest
from lorefern.adapters.base import RemoteDoc, RemoteDocs
from lorefern.adapters.sources import DriveSource, NotionSource
from lorefern.config import Settings
from lorefern.models import Document, Source

TEXT = "Every person gets 25 days of paid leave a year, booked through the shared calendar.\n"


def drive_with(handler) -> DriveSource:
    return DriveSource(Settings(_env_file=None, drive_token="tok"), client=httpx.Client(transport=httpx.MockTransport(handler), base_url="http://drive.test"))


def notion_with(handler) -> NotionSource:
    return NotionSource(Settings(_env_file=None, notion_token="tok"), client=httpx.Client(transport=httpx.MockTransport(handler), base_url="http://notion.test"))


def listing(files: list[dict], token: str | None = None) -> httpx.Response:
    return httpx.Response(200, json={"files": files, **({"nextPageToken": token} if token else {})})


def gdoc(i: str) -> dict:
    return {"id": i, "name": f"Doc {i}", "mimeType": "application/vnd.google-apps.document", "modifiedTime": "2026-11-01T00:00:00Z"}


def make_source(s, kind="drive") -> Source:
    x = Source(kind=kind, name=f"{kind} source", uri="", default_tag="company")
    s.add(x)
    s.flush()
    return x


def stored(s, source) -> set[str]:
    return {d.external_id for d in s.scalars(select(Document).where(Document.source_id == source.id))}


def test_a_file_that_could_not_be_exported_keeps_its_old_copy(ctx):
    state = {"fail": False}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/drive/v3/files":
            return listing([gdoc("aaaaaa"), gdoc("bbbbbb")])
        if "bbbbbb" in req.url.path and state["fail"]:
            return httpx.Response(429, json={"error": {"code": 429}})
        return httpx.Response(200, text=TEXT)

    drive = drive_with(handler)
    with ctx.factory() as s:
        src = make_source(s)
        first = drive.list_documents()
        assert first.complete and len(first) == 2
        ingest.ingest_remote(s, src, first)
        state["fail"] = True
        second = drive.list_documents()
        assert not second.complete and [d.external_id for d in second] == ["aaaaaa"]
        res = ingest.ingest_remote(s, src, second)
        assert res["removed"] == 0 and res["incomplete"] == 1 and stored(s, src) == {"aaaaaa", "bbbbbb"}
        state["fail"] = False
        third = drive.list_documents()
        assert third.complete
        assert ingest.ingest_remote(s, src, RemoteDocs([third[0]], complete=True))["removed"] == 1  # a complete read still removes what is really gone


def test_the_page_folder_and_depth_limits_make_a_read_incomplete(monkeypatch):
    def endless(req: httpx.Request) -> httpx.Response:
        return listing([{"id": "ffffff", "name": "x", "mimeType": "application/octet-stream"}], token="more")

    monkeypatch.setattr(DriveSource, "MAX_PAGES", 3)
    assert not drive_with(endless).list_documents().complete

    folder = lambda i: {"id": i, "name": i, "mimeType": "application/vnd.google-apps.folder"}  # noqa: E731

    def tree(req: httpx.Request) -> httpx.Response:
        parent = req.url.params["q"].split("'")[1]
        return listing([folder("child1" + parent[-3:]), folder("child2" + parent[-3:])] if len(parent) == 6 else [])

    monkeypatch.setattr(DriveSource, "MAX_PAGES", 50)
    monkeypatch.setattr(DriveSource, "MAX_FOLDERS", 2)
    assert not drive_with(tree).list_documents(["rootaa"]).complete
    monkeypatch.setattr(DriveSource, "MAX_FOLDERS", 200)
    monkeypatch.setattr(DriveSource, "MAX_DEPTH", 0)
    assert not drive_with(tree).list_documents(["rootaa"]).complete
    monkeypatch.setattr(DriveSource, "MAX_DEPTH", 6)
    assert drive_with(tree).list_documents(["rootaa"]).complete


def test_a_file_over_the_size_limit_is_not_downloaded_in_full(monkeypatch):
    monkeypatch.setattr(DriveSource, "MAX_BYTES", 1000)
    pulled: list[int] = []

    class Endless(httpx.SyncByteStream):
        def __iter__(self):
            for _ in range(10_000):
                pulled.append(1)
                yield b"x" * 100

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/drive/v3/files":
            return listing([gdoc("aaaaaa")])
        return httpx.Response(200, stream=Endless())  # no length header: the reader must stop by itself

    docs = drive_with(handler).list_documents()
    assert len(docs) == 0 and docs.complete  # left out on purpose, which is not a failed read
    assert len(pulled) <= 12  # about 1000 bytes of 100 byte chunks, not the 1 MB on offer


def test_a_declared_size_over_the_limit_is_refused_before_any_body_is_read(monkeypatch):
    monkeypatch.setattr(DriveSource, "MAX_BYTES", 1000)
    pulled: list[int] = []

    class Big(httpx.SyncByteStream):
        def __iter__(self):
            pulled.append(1)
            yield b"x" * 10

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/drive/v3/files":
            return listing([gdoc("aaaaaa")])
        return httpx.Response(200, headers={"content-length": "5000000"}, stream=Big())

    assert len(drive_with(handler).list_documents()) == 0 and pulled == []


def notion_pages(n: int) -> list[dict]:
    return [{"object": "page", "id": f"p{i:02d}", "last_edited_time": "2026-11-01T00:00:00Z", "properties": {"title": {"title": [{"plain_text": f"Page {i}"}]}}} for i in range(n)]


def block(text: str) -> dict:
    return {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": text}]}}


def test_a_notion_page_that_could_not_be_read_keeps_its_old_copy(ctx):
    state = {"fail": False}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/v1/search":
            return httpx.Response(200, json={"results": notion_pages(2), "has_more": False})
        if "p01" in req.url.path and state["fail"]:
            return httpx.Response(503, json={})
        return httpx.Response(200, json={"results": [block(TEXT)], "has_more": False})

    notion = notion_with(handler)
    with ctx.factory() as s:
        src = make_source(s, "notion")
        ingest.ingest_remote(s, src, notion.list_documents())
        assert stored(s, src) == {"p00", "p01"}
        state["fail"] = True
        again = notion.list_documents()
        assert not again.complete and len(again) == 1
        assert ingest.ingest_remote(s, src, again)["removed"] == 0 and stored(s, src) == {"p00", "p01"}


def test_a_long_notion_page_is_read_in_every_block_page_and_a_search_limit_is_reported(monkeypatch):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/v1/search":
            return httpx.Response(200, json={"results": notion_pages(1), "has_more": True, "next_cursor": "c"})
        cursor = req.url.params.get("start_cursor")
        if not cursor:
            return httpx.Response(200, json={"results": [block("First block of the page.")], "has_more": True, "next_cursor": "n2"})
        return httpx.Response(200, json={"results": [block("Second block, past the first hundred.")], "has_more": False})

    monkeypatch.setattr(NotionSource, "MAX_PAGES", 2)
    docs = notion_with(handler).list_documents()
    assert "Second block" in docs[0].text  # the text past the first hundred blocks is no longer dropped
    assert not docs.complete  # and the search limit is reported


def test_a_plain_list_from_another_adapter_still_removes_what_is_gone(ctx):
    with ctx.factory() as s:
        src = make_source(s)
        ingest.ingest_remote(s, src, [RemoteDoc("aaaaaa", "A", TEXT), RemoteDoc("bbbbbb", "B", TEXT)])
        assert ingest.ingest_remote(s, src, [RemoteDoc("aaaaaa", "A", TEXT)])["removed"] == 1


def test_the_sources_page_says_when_a_read_stopped_early(tmp_path, monkeypatch):
    from real_install import Install

    i = Install(tmp_path, knowledge_adapter="drive", drive_token="tok")
    i.ctx.adapters.knowledge = type("Partial", (), {"list_documents": lambda self, scope=None: RemoteDocs([RemoteDoc("aaaaaa", "A", TEXT)], complete=False), "healthcheck": lambda self: (True, "")})()
    sid = i.add_source("Drive", "", kind="drive")
    res = i.sync(sid)
    assert res["incomplete"] == 1
    row = next(x for x in i.get("owner", "/api/sources").json() if x["id"] == sid)
    assert "stopped before it saw everything" in row["error"] and row["status"] == "ready"


# ---- F5: the quick demo says what is true about the sign in hint

def test_the_quick_demo_sets_the_sign_in_hint_when_the_web_app_is_built_and_names_the_password():
    from pathlib import Path

    from lorefern.api.routes_auth import DEMO_PASSWORD

    root = Path(__file__).resolve().parents[3]
    doc = (root / "docs/01-QUICK-DEMO.md").read_text()
    build = next(ln for ln in doc.splitlines() if ln.startswith("3."))
    start = next(ln for ln in doc.splitlines() if ln.startswith("5."))
    assert "NEXT_PUBLIC_DEMO_HINT=1 pnpm build" in build  # Next.js copies NEXT_PUBLIC_ values into the page at build time
    assert "NEXT_PUBLIC_DEMO_HINT" not in start
    assert DEMO_PASSWORD in doc
    page = (root / "apps/web/app/login/page.tsx").read_text()
    assert 'process.env.NEXT_PUBLIC_DEMO_HINT === "1"' in page and DEMO_PASSWORD in page
    assert "built" in (root / "docs/04-ENVIRONMENT-VARIABLES.md").read_text().split("## NEXT_PUBLIC_DEMO_HINT")[1].split("##")[0]


# ---- F7: what the model is sent, what the audit log and the approval count show, what the folder page counts

def test_the_model_that_names_a_process_only_sees_company_wide_evidence(world):
    from lorefern import sops

    sent: list[list[str]] = []

    def recorder(label, evidence):
        sent.append(list(evidence))
        return ""

    with world.factory() as s:
        sops.detect(s, world.today(s), world.settings, wording=recorder)
        from lorefern.models import Process

        rows = list(s.scalars(select(Process)))
    company = {e["text"] for p in rows for e in p.evidence if e["tag"] == "company"}
    other = {e["text"] for p in rows for e in p.evidence if e["tag"] != "company"} - company
    assert other, "the demo has processes with restricted evidence, so this test means something"
    assert sent and {x for call in sent for x in call} <= company
    assert not ({x for call in sent for x in call} & other)


def test_the_audit_log_hides_entries_about_a_source_the_person_cannot_see(tmp_path):
    from real_install import Install

    i = Install(tmp_path, {"hr/review.md": "# Review\n\nPay reviews happen in January for everyone.\n", "wiki/guide.md": "---\nvisibility: company\n---\n# Guide\n\nStart here.\n"})
    hr = i.add_source("HR share", "hr", tag="people")
    wiki = i.add_source("Wiki", "wiki")
    i.sync(hr)
    i.sync(wiki)
    assert i.c.patch(f"/api/sources/{hr}", headers=i.h["owner"], json={"untagged_tag": "people"}).status_code == 200
    seen_by = lambda who: {e["target"] for e in i.get(who, "/api/audit?limit=500").json() if (e["target"] or "").startswith("source:")}  # noqa: E731
    assert {f"source:{hr}", f"source:{wiki}"} <= seen_by("owner")
    assert f"source:{hr}" not in seen_by("leadership") and f"source:{wiki}" in seen_by("leadership")
    blob = i.get("leadership", "/api/audit?limit=500").text
    assert '"tag":"people"' not in blob.replace(" ", "")


def test_pending_approvals_are_counted_and_listed_only_for_people_who_may_see_their_tasks(client):
    from lorefern.models import Reminder, Task
    from sendora_core.approvals import request_approval

    from conftest import login

    ctx = client.app.state.ctx
    with ctx.factory() as s:
        t = Task(title="Settle the salary review", status="open", tag="people", created_at=ctx.now(s), updated_at=ctx.now(s))
        s.add(t)
        s.flush()
        r = Reminder(task_id=t.id, kind="overdue", on_date=ctx.today(s), body="x", status="drafted")
        s.add(r)
        s.flush()
        request_approval(s, "reminders.send", "Send 1 task reminders", {"ids": [r.id]}, "low", "owner@example.test")
        s.commit()
    o, lead, st = login(client), login(client, "approver@example.test"), login(client, "staff@example.test")
    count = lambda h: client.get("/api/overview", headers=h).json()["pending_approvals"]  # noqa: E731
    assert count(o) >= 1 and count(lead) == count(o) - 1 and count(st) == 0
    assert any(a["status"] == "pending" for a in client.get("/api/approvals", headers=o).json())
    assert not any(a["payload"].get("ids") and r.id in a["payload"]["ids"] for a in client.get("/api/approvals", headers=lead).json())
    assert client.get("/api/approvals", headers=st).status_code == 403


def test_the_folder_page_works_when_the_source_has_its_own_path_and_counts_only_what_the_person_sees(tmp_path):
    from real_install import Install

    files = {"company/open.md": "---\nvisibility: company\nowner: A\nreview_by: 2030-01-01\n---\n# Open\n\nEveryone reads this.\n", "company/hr/.visibility": "people\n",
             "company/hr/pay.md": "---\nvisibility: people\nowner: A\nreview_by: 2030-01-01\n---\n# Pay\n\nSecret pay words.\n", "company/INDEX.md": "# Index\n\n"}
    i = Install(tmp_path, files)
    i.sync(i.add_source("Company", "company"))
    owner, lead = i.get("owner", "/api/company-folder").json(), i.get("leadership", "/api/company-folder").json()
    assert owner["documents"] == 2 and lead["documents"] == 1 and lead["documents_visible"] == 1  # leadership may not see `people`, so the folder page does not count the file


# ---- F8: search statistics, the word weights cache, the documents filter, the scan bound

def test_the_documents_filter_runs_before_the_limit(tmp_path):
    from real_install import Install

    files = {f"kb/a{i:02d}.md": f"---\nvisibility: company\n---\n# Note {i}\n\nPlain words number {i} here.\n" for i in range(12)}
    files["kb/zz-budget.md"] = "---\nvisibility: company\n---\n# Budget plan\n\nThe yearly budget words here.\n"
    i = Install(tmp_path, files)
    i.sync(i.add_source("KB", "kb"))
    assert [d["title"] for d in i.get("staff", "/api/documents?q=budget&limit=3").json()] == ["Budget plan"]  # it sorts last, after the limit of 3
    assert len(i.get("staff", "/api/documents?limit=3").json()) == 3
    assert i.get("staff", "/api/documents?q=100%25").json() == []  # a percent sign is text, not a wildcard


def test_a_restricted_passage_never_changes_the_scores_of_what_a_person_can_search(tmp_path):
    from real_install import Install

    open_files = {"kb/a.md": "---\nvisibility: company\n---\n# Leave\n\nEvery person gets paid leave each year for rest.\n", "kb/b.md": "---\nvisibility: company\n---\n# Travel\n\nBook flights early for every trip.\n"}
    secret = {"kb/s.md": "---\nvisibility: people\n---\n# Pay\n\nLeave leave leave pay for each person every year, leave pay leave.\n"}
    from lorefern import search
    from lorefern.visibility import allowed_tags

    def scores(files):
        i = Install(tmp_path / ("x" if len(files) > 2 else "y"), files)
        i.sync(i.add_source("KB", "kb"))
        with i.ctx.factory() as s:
            return [(h.chunk_id, round(h.bm25, 9), round(h.cosine, 9)) for h in search.search(s, "paid leave each year", allowed_tags("staff"), 6)]

    assert scores(open_files) == scores({**open_files, **secret})


def test_a_retag_clears_the_word_weights_that_were_stored_for_the_old_tags(client):
    from lorefern import search, visibility
    from lorefern.models import Source
    from conftest import login

    o, ctx = login(client), client.app.state.ctx
    with ctx.factory() as s:
        before, _ = search.idf_table(s, visibility.allowed_tags("staff"))
        folder = s.scalar(select(Source).where(Source.kind == "folder"))
    assert client.patch(f"/api/sources/{folder.id}", headers=o, json={"default_tag": "leadership"}).status_code == 200
    with ctx.factory() as s:
        after, _ = search.idf_table(s, visibility.allowed_tags("staff"))
    assert after != before and len(after) < len(before)  # staff can no longer see the folder, and the cache did not keep serving the old weights


def test_the_vector_step_reads_a_bounded_number_of_passages(client, monkeypatch):
    from lorefern import search
    from lorefern.visibility import allowed_tags

    ctx = client.app.state.ctx
    monkeypatch.setattr(search, "MAX_VECTOR_SCAN", 5)
    seen: list[int] = []
    real = search.cosine
    monkeypatch.setattr(search, "cosine", lambda a, b: (seen.append(1), real(a, b))[1])
    with ctx.factory() as s:
        search.search(s, "How are databases backed up?", allowed_tags("owner"), 6)
    assert 0 < len(seen) <= 5 + 12  # the scan, plus the full text hits that are scored on their own
