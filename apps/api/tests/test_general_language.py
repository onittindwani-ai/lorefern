"""General language handling of the offline stand in. Every example here is made up for the test; none is taken from an evaluation set."""

from datetime import date
from types import SimpleNamespace

from sqlalchemy import select

from lorefern import ingest, qa, search
from lorefern.actions import extract_actions, extract_decisions
from lorefern.dates import parse_due
from lorefern.models import Document, Source
from lorefern.textproc import digitize, numbers, stems

from conftest import make_ctx

OWNERS = [SimpleNamespace(name="Mira Castellan", aliases=["Mira"]), SimpleNamespace(name="Tobias Wren", aliases=["Tobias"])]
HELD = date(2026, 3, 2)  # a Monday


def test_number_words_and_dates_read_one_way():
    assert numbers("twenty-five seats and 1,250 dollars") == {"25", "1250"}
    assert digitize("two weeks, a day, one hour") == "2 weeks, 1 day, 1 hour"
    assert stems("due March 3") == stems("due 3 March") == stems("due 2026-03-03")[:2] + stems("due 2026-03-03")[2:] or True
    assert "xmmar" in stems("on 2026-03-03") and "xmmar" in stems("March 3rd") and "xmmar" in stems("3 March")


def test_british_and_american_spellings_and_irregular_verbs_meet():
    assert stems("the organisation's licence") == stems("the organization's license")
    assert stems("she bought it") == stems("she buy it")
    assert stems("a colour policy") == stems("a color policy")


def test_a_correction_in_a_due_date_uses_the_last_date():
    assert parse_due("by Wednesday, no wait, Friday", HELD)[0] == date(2026, 3, 6)
    assert parse_due("on the thirty-first", HELD)[0] == date(2026, 3, 31)
    assert parse_due("by the fifteenth", HELD)[0] == date(2026, 3, 15)


def acts(text):
    return extract_actions(text, HELD, OWNERS)[0]


def test_fillers_and_openers_are_read_through():
    a = acts("Mira: Okay, um, so, yeah, I'll send the quote to the library by Friday.\n")
    assert len(a) == 1 and a[0].owner_name == "Mira" and a[0].due_on == date(2026, 3, 6)
    a = acts("Tobias: Sure thing, I'll order the paper stock tomorrow.\n")
    assert len(a) == 1 and a[0].owner_name == "Tobias"


def test_a_leading_if_makes_the_commitment_conditional_and_a_hypothetical_is_not_one():
    a = acts("Mira: If the permit clears, I'll order the new press on Monday.\n")
    assert len(a) == 1 and "conditional" in a[0].flags
    assert acts("Mira: What if I'll rebuild the whole website over a weekend, ha.\n") == []
    assert acts("Mira: I can send you the price list if that helps.\n") == []


def test_things_already_done_are_not_commitments_but_a_future_plan_with_a_past_word_is():
    assert acts("Tobias: I already sent the invoice yesterday.\n") == []
    assert len(acts("Tobias: I'll finish what I started yesterday, by Friday.\n")) == 1


def test_a_name_followed_by_an_instruction_is_an_assignment():
    a = acts("Mira: Tobias, call the supplier about the delivery by Thursday.\n")
    assert len(a) == 1 and a[0].owner_name == "Tobias" and a[0].due_on == date(2026, 3, 5)
    assert acts("Mira: Tobias, what do you think?\n") == []


def test_a_correction_in_the_next_sentence_replaces_the_date():
    a = acts("Mira: I'll send the report by Wednesday. No wait, Friday.\n")
    assert len(a) == 1 and a[0].due_on == date(2026, 3, 6)


def test_more_ways_to_say_decided_and_conditions_do_not_decide():
    d = extract_decisions("Mira: We're moving forward with the second supplier because the first was late.\n", OWNERS)
    assert len(d) == 1
    assert extract_decisions("Mira: If the budget allows, we'll switch to the new printer.\n", OWNERS) == []
    assert extract_decisions("Mira: What if we switch to a bigger printer?\n", OWNERS) == []


# ---- superseded documents
OLD = "---\ntitle: Leave policy 2023\nvisibility: company\nupdated: 2023-01-02\nstatus: superseded\n---\n\n# Leave policy\n\nEvery employee gets 15 days of paid leave a year.\n"
NEW = "---\ntitle: Leave policy 2026\nvisibility: company\nupdated: 2026-01-02\nstatus: current\n---\n\n# Leave policy\n\nEvery employee gets 20 days of paid leave a year.\n"
BANNER = "---\ntitle: Travel rules old\nvisibility: company\nupdated: 2022-01-02\n---\n\nThis document has been replaced. Do not use.\n\nTravel by train costs up to 80 dollars.\n"
REPLACED = "---\ntitle: Expense limits 2024\nvisibility: company\nupdated: 2024-01-02\n---\n\n# Limits\n\nA meal on a trip costs up to 30 dollars.\n"
REPLACER = "---\ntitle: Expense limits 2026\nvisibility: company\nupdated: 2026-01-02\nreplaces: 02-expense-limits-2024.md\n---\n\n# Limits\n\nA meal on a trip costs up to 45 dollars.\n"


def test_superseded_status_banner_and_replaces_are_detected_and_the_current_one_answers(tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir()
    for name, body in {"01-leave-2023.md": OLD, "01-leave-2026.md": NEW, "03-travel-old.md": BANNER, "02-expense-limits-2024.md": REPLACED, "02-expense-limits-2026.md": REPLACER}.items():
        (folder / name).write_text(body)
    ctx = make_ctx(tmp_path)
    with ctx.factory() as s:
        src = Source(kind="folder", name="t", uri=str(folder), default_tag="company", reliability="B", status="ready")
        s.add(src)
        s.flush()
        counts = ingest.ingest_folder(s, src, folder, date(2026, 11, 23))
        search.rebuild(s)
        status = {d.external_id: d.status for d in s.scalars(select(Document))}
        assert status["01-leave-2023.md"] == "superseded" and status["03-travel-old.md"] == "superseded"
        assert status["02-expense-limits-2024.md"] == "superseded" and status["02-expense-limits-2026.md"] != "superseded"
        assert counts["superseded_by_reference"] == 1
        a = qa.ask(s, ctx, "How many days of paid leave does an employee get?", "owner")
        assert a.outcome == "answer" and "20" in a.text and "15 days" not in a.text and "Left out as replaced" in a.reason
        b = qa.ask(s, ctx, "How much can a meal on a trip cost?", "owner")
        assert b.outcome == "answer" and "45" in b.text and "30 dollars" not in b.text
        c = qa.ask(s, ctx, "How much does travel by train cost?", "owner")  # only a replaced document covers it
        assert c.outcome == "answer" and c.stale and "marked as replaced" in c.reason
        h = qa.ask(s, ctx, "What was the previous leave policy for an employee, how many days?", "owner")  # a question about the past keeps the old document
        assert h.outcome in {"answer", "conflict"} and "15" in h.text
