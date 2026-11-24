from datetime import date, timedelta

import pytest

from lorefern.dates import parse_due

TUE = date(2026, 11, 10)  # a Tuesday


@pytest.mark.parametrize("text,expected", [
    ("by Friday", date(2026, 11, 13)), ("by next Friday", date(2026, 11, 20)), ("tomorrow", date(2026, 11, 11)), ("today", TUE), ("end of day", TUE), ("by the end of the week", date(2026, 11, 13)),
    ("end of the month", date(2026, 11, 30)), ("next week", date(2026, 11, 20)), ("in two weeks", date(2026, 11, 24)), ("in 3 days", date(2026, 11, 13)), ("the 14th", date(2026, 11, 14)),
    ("by the 5th", date(2026, 12, 5)), ("Dec 4", date(2026, 12, 4)), ("4 December", date(2026, 12, 4)), ("2026-12-04", date(2026, 12, 4)), ("on Tuesday", date(2026, 11, 17)), ("this week", date(2026, 11, 13)),
])
def test_known_phrases(text, expected):
    assert parse_due(f"I will do it {text}", TUE)[0] == expected


@pytest.mark.parametrize("text", ["soon", "as soon as you can", "when you can", "at some point"])
def test_vague_words_give_no_date_but_are_kept(text):
    d, raw = parse_due(f"Please do it {text}", TUE)
    assert d is None and raw


def test_no_date_words_give_nothing():
    assert parse_due("I will write the report", TUE) == (None, "")


def test_an_impossible_date_gives_none_not_a_crash():
    assert parse_due("by 2026-02-31", TUE)[0] is None


def test_every_weekday_name_lands_on_that_weekday_after_the_meeting():
    for offset in range(14):  # property: any meeting day, any weekday name
        held = TUE + timedelta(days=offset)
        for name, wd in (("monday", 0), ("wednesday", 2), ("friday", 4), ("sunday", 6)):
            d = parse_due(f"by {name}", held)[0]
            assert d.weekday() == wd and held < d <= held + timedelta(days=7)


def test_next_weekday_is_in_the_following_calendar_week():
    for offset in range(14):
        held = TUE + timedelta(days=offset)
        d = parse_due("by next friday", held)[0]
        assert d.weekday() == 4 and d > held and (d - (held - timedelta(days=held.weekday()))).days >= 11


def test_relative_dates_never_go_back_in_time():
    for phrase in ["tomorrow", "next week", "in 5 days", "end of the month", "the 3rd", "Jan 2"]:
        for offset in range(0, 400, 7):
            held = date(2026, 1, 1) + timedelta(days=offset)
            d = parse_due(phrase, held)[0]
            assert d is None or d >= held, (phrase, held, d)
