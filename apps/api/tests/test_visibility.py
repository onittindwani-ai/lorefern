"""The visibility boundary, tested hard: a restricted document never shows up in search, answers, citations, lists, counts or direct links of a role that may not see it."""

import json

import pytest
from sqlalchemy import select

from lorefern import qa, search, visibility
from lorefern.models import Chunk, Decision, Document, Meeting, Task
from conftest import login

SECRETS = ["98,000", "82,000", "641,000", "Larkspur", "2.4 million", "performance plan", "22nd retainer client", "70,000", "48,000", "Dana's raise", "6 percent from January", "9 months of costs"]
QUESTIONS = ["What salary does Priya earn?", "Did anyone make an offer to buy the company?", "Who is on a performance plan?", "How much is the marketing budget?", "What is the salary band for developers?", "When do we hire?",
             "How long can the company run on cash?", "Tell me about Larkspur Group", "payroll total", "raise for Dana"]


def test_the_audience_tag_table_is_what_the_docs_say():
    assert visibility.allowed_tags("staff") == ("company", "clients")
    assert "people" not in visibility.allowed_tags("leadership") and "people" in visibility.allowed_tags("owner")
    assert visibility.allowed_tags("nobody") == visibility.allowed_tags("staff")  # unknown audiences get the narrowest set
    assert visibility.allowed_tags("") == visibility.allowed_tags("staff")


def test_search_returns_only_chunks_of_allowed_tags_for_every_audience_and_question(ro):
    with ro.factory() as s:
        tag_of = dict(s.execute(select(Chunk.id, Chunk.tag)).all())
        for aud in visibility.AUDIENCES:
            tags = visibility.allowed_tags(aud)
            for q in QUESTIONS + ["salary", "budget", "offer", "retainer", "performance", "payroll", "cash", "raise"]:
                for h in search.search(s, q, tags, 12):
                    assert tag_of[h.chunk_id] in tags, (aud, q)


def test_answers_for_staff_never_contain_a_restricted_fact(ro):
    with ro.factory() as s:
        for q in QUESTIONS:
            a = qa.ask(s, ro, q, "staff")
            blob = json.dumps(a.as_dict())
            assert not any(x in blob for x in SECRETS), (q, a.text)
            # a reworded question can still hit an unrelated visible sentence (the offline matcher is lexical): that is a wrong answer, not a leak, and it is measured in the held out set


def test_finance_cannot_read_leadership_or_people_facts(ro):
    with ro.factory() as s:
        for q in ["What does leadership plan about hiring?", "Did anyone offer to buy us?", "Who is on a performance plan?", "What is the salary band for developers?"]:
            blob = json.dumps(qa.ask(s, ro, q, "finance").as_dict())
            assert not any(x in blob for x in ("22nd retainer client", "Larkspur", "performance plan", "70,000")), q


def test_the_not_found_text_is_the_same_whether_missing_or_restricted(ro):
    with ro.factory() as s:
        restricted = qa.ask(s, ro, "What salary does Priya earn?", "staff")
        missing = qa.ask(s, ro, "Which airline do we use for travel?", "staff")
        assert restricted.text == missing.text and restricted.citations == [] and missing.citations == []


def test_the_owner_and_leadership_do_see_what_staff_may_not(ro):
    with ro.factory() as s:
        assert "98,000" in qa.ask(s, ro, "What salary does Priya earn?", "finance").text
        assert "2.4 million" in qa.ask(s, ro, "Did Larkspur Group make an offer to buy the company?", "owner").text


def test_idf_weights_ignore_restricted_chunks(ro):
    with ro.factory() as s:
        staff, _ = search.idf_table(s, visibility.allowed_tags("staff"))
        owner, _ = search.idf_table(s, visibility.allowed_tags("owner"))
        assert "larkspur" not in staff and "larkspur" in owner


@pytest.mark.parametrize("who,expected_status", [("staff@example.test", 404), ("finance@example.test", 404)])
def test_direct_links_to_restricted_rows_answer_404(client, who, expected_status):
    o, h = login(client), login(client, who)
    docs = {d["tag"]: d["id"] for d in client.get("/api/documents", headers=o).json()}
    for tag in ("leadership", "people"):
        assert client.get(f"/api/documents/{docs[tag]}", headers=h).status_code == expected_status
    # the same status as a row that does not exist
    assert client.get("/api/documents/99999", headers=h).status_code == 404


def test_every_read_route_hides_restricted_rows_from_staff_and_finance(client):
    o = login(client)
    for who in ("staff@example.test", "finance@example.test"):
        h = login(client, who)
        allowed = set(visibility.allowed_tags("staff" if who.startswith("staff") else "finance"))
        for path, tagkey in (("/api/documents", "tag"), ("/api/tasks", "tag"), ("/api/meetings", "tag"), ("/api/decisions", "tag")):
            rows = client.get(path, headers=h).json()
            assert rows and {r[tagkey] for r in rows} <= allowed, (who, path)
        blob = " ".join(client.get(p, headers=h).text for p in ("/api/documents", "/api/tasks", "/api/meetings", "/api/decisions", "/api/stuck", "/api/sops", "/api/reviews", "/api/reminders", "/api/sources", "/api/overview", "/api/owners"))
        assert not any(x in blob for x in SECRETS), who
    ids = {t["id"] for t in client.get("/api/tasks", headers=o).json() if t["tag"] == "leadership"}
    h = login(client, "staff@example.test")
    for tid in ids:
        assert client.get(f"/api/tasks/{tid}", headers=h).status_code == 404
    for m in client.get("/api/meetings", headers=o).json():
        if m["tag"] == "leadership":
            assert client.get(f"/api/meetings/{m['id']}", headers=h).status_code == 404


def test_counts_in_the_overview_only_count_visible_rows(client):
    o, h = login(client), login(client, "staff@example.test")
    ov_o, ov_s = client.get("/api/overview", headers=o).json(), client.get("/api/overview", headers=h).json()
    assert ov_s["documents"] < ov_o["documents"] and ov_s["meetings"] < ov_o["meetings"] and ov_s["decisions"] < ov_o["decisions"]


def test_stuck_evidence_and_overload_lines_do_not_name_hidden_tasks(client):
    h = login(client, "staff@example.test")
    o = login(client)
    all_tasks = client.get("/api/tasks", headers=o).json()
    hidden = {t["id"] for t in all_tasks if t["tag"] not in {"company", "clients"}}
    hidden_titles = {t["title"] for t in all_tasks if t["tag"] not in {"company", "clients"}}
    for s in client.get("/api/stuck", headers=h).json():
        assert not (set(s["task_ids"]) & hidden) and (s["task_id"] not in hidden)
        for title in hidden_titles:
            assert title not in s["evidence"]


def test_reviews_are_scoped_and_company_review_has_only_company_evidence(client):
    h, o = login(client, "staff@example.test"), login(client)
    mine = client.get("/api/reviews", headers=h).json()
    assert [r["scope"] for r in mine] == ["company"]
    assert {"company", "leadership"} == {r["scope"] for r in client.get("/api/reviews", headers=o).json()}
    body = client.get(f"/api/reviews/{mine[0]['id']}", headers=h).json()["body"]
    tasks = {t["id"]: t for t in client.get("/api/tasks", headers=o).json()}
    import re
    for tid in re.findall(r"\[T(\d+)\]", body):
        assert tasks[int(tid)]["tag"] == "company"
    lead = next(r for r in client.get("/api/reviews", headers=o).json() if r["scope"] == "leadership")
    assert client.get(f"/api/reviews/{lead['id']}", headers=h).status_code == 404


def test_preview_as_a_narrower_audience_works_and_a_wider_one_does_not(client):
    o, st = login(client), login(client, "staff@example.test")
    full = client.get("/api/documents", headers=o).json()
    narrow = client.get("/api/documents?as=staff", headers=o).json()
    assert 0 < len(narrow) < len(full) and {d["tag"] for d in narrow} <= {"company", "clients"}
    wide = client.get("/api/documents?as=owner", headers=st).json()  # staff cannot widen
    assert {d["tag"] for d in wide} <= {"company", "clients"}


def test_previewing_cannot_change_anything(client):
    o = login(client)
    t = next(t for t in client.get("/api/tasks?status=proposed", headers=o).json())
    assert client.post(f"/api/tasks/{t['id']}/approve?as=staff", headers=o, json={}).status_code == 403
    assert client.post(f"/api/tasks/{t['id']}/approve", headers=o, json={}).status_code == 200


def test_unknown_email_is_staff_and_cannot_sign_in_outside_demo(tmp_path):
    from lorefern.config import Settings
    s = Settings(_env_file=None, demo_mode=False, owner_email="o@x.test")
    assert visibility.audience_of(s, "nobody@x.test") == "staff" and visibility.audience_of(s, "O@X.TEST") == "owner"
    assert set(s.members()) == {"o@x.test"}  # the demo accounts do not exist outside demo mode
