"""Turn a due phrase like "by next Friday" into a date, relative to the day of the meeting. Plain rules, tested.

Conventions (decided defaults: working week Monday to Friday, weeks start on Monday, "Friday" is the next Friday after the meeting):
  "Friday", "this Friday", "by Friday"   the next Friday strictly after the meeting day (a meeting on a Friday means the Friday a week later)
  "next Friday"                          that weekday in the calendar week after the meeting's week
  "end of the week", "EOW"               the Friday of the meeting's week (the meeting day if it is already past Friday)
  "end of the month", "next week"        last day of the month; Friday of next week
  "tomorrow", "today", "end of day"      meeting day plus 1, meeting day, meeting day
  "in 3 days", "in two weeks"            plus that many days or weeks
  "the 14th", "on the 14th"              the next 14th after the meeting day
  "Dec 4", "4 December", "2026-12-04"    that date, in the meeting's year or the next one when already past
Vague words (soon, asap, when you can, at some point) give no date and are kept as the raw phrase.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

WEEKDAYS = {n: i for i, n in enumerate(["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"])}
WEEKDAYS.update({"mon": 0, "tue": 1, "tues": 1, "wed": 2, "thu": 3, "thur": 3, "thurs": 3, "fri": 4, "sat": 5, "sun": 6})
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
NUMWORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "a": 1}
VAGUE = re.compile(r"\b(soon|asap|as soon as (?:possible|you can)|when you can|at some point|sometime|eventually|whenever|in due course)\b", re.I)
_WD = "|".join(sorted(WEEKDAYS, key=len, reverse=True))
_MO = "|".join(sorted(MONTHS, key=len, reverse=True))

_ORD_UNITS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9}
_ORD_TEENS = {"tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18, "nineteenth": 19, "twentieth": 20, "thirtieth": 30}
ORDINAL_WORDS = {**{k: v for k, v in _ORD_UNITS.items() if v >= 4}, **_ORD_TEENS}
for _t, _n in (("twenty", 20), ("thirty", 30)):
    for _k, _v in _ORD_UNITS.items():
        if _n + _v <= 31:
            ORDINAL_WORDS[f"{_t}-{_k}"] = _n + _v
            ORDINAL_WORDS[f"{_t} {_k}"] = _n + _v
_OW = "|".join(sorted(ORDINAL_WORDS, key=len, reverse=True))
CORRECTION = re.compile(r"\b(?:no,? wait|wait,? no|no no|sorry|scratch that|make that|i mean|rather|correction|actually,? no|no,? actually)\b[,:]?\s*", re.I)

PATTERNS = [
    ("iso", re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")),
    ("monthday", re.compile(rf"\b(?:on |by |before |until )?({_MO})\.? (\d{{1,2}})(?:st|nd|rd|th)?\b", re.I)),
    ("daymonth", re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)? (?:of )?({_MO})\b", re.I)),
    ("nextweekday", re.compile(rf"\bnext ({_WD})\b", re.I)),
    ("inN", re.compile(r"\bin (\d+|a|one|two|three|four|five|six|seven|eight|nine|ten) (day|days|week|weeks|business days)\b", re.I)),
    ("eow", re.compile(r"\b(end of (?:the |this )?week|eow|this week)\b", re.I)),
    ("eom", re.compile(r"\b(end of (?:the |this )?month|eom)\b", re.I)),
    ("nextweek", re.compile(r"\b(?:by |before |within )?next week\b", re.I)),
    ("tomorrow", re.compile(r"\btomorrow\b", re.I)),
    ("today", re.compile(r"\b(today|end of (?:the )?day|eod|tonight)\b", re.I)),
    ("ordinalword", re.compile(rf"\b(?:on |by |before |until )?the ({_OW})\b", re.I)),
    ("ordinal", re.compile(r"\b(?:on |by |before |until )?the (\d{1,2})(?:st|nd|rd|th)\b", re.I)),
    ("weekday", re.compile(rf"\b(?:this |on |by |before |until )?({_WD})\b", re.I)),
]


def _next_weekday(d: date, wd: int) -> date:
    delta = (wd - d.weekday()) % 7
    return d + timedelta(days=delta or 7)


def _friday_of_week(d: date) -> date:
    return d + timedelta(days=(4 - d.weekday())) if d.weekday() <= 4 else d


def _safe(y: int, m: int, day: int) -> date | None:
    try:
        return date(y, m, day)
    except ValueError:
        return None


def parse_due(text: str, held_on: date) -> tuple[date | None, str]:
    """Return (date or None, the phrase that was read). The phrase is exactly as written in `text`.
    When the speaker corrects themselves ("Wednesday, no wait, Friday") the last stated date wins."""
    marks = list(CORRECTION.finditer(text))
    if marks:
        d, raw = _parse_due(text[marks[-1].end():], held_on)
        if d is not None:
            return d, raw
    return _parse_due(text, held_on)


def _parse_due(text: str, held_on: date) -> tuple[date | None, str]:
    for name, rx in PATTERNS:
        m = rx.search(text)
        if not m:
            continue
        raw = m.group(0).strip()
        g = m.groups()
        if name == "iso":
            return _safe(int(g[0]), int(g[1]), int(g[2])), raw
        if name in {"monthday", "daymonth"}:
            mon, day = (MONTHS[g[0].lower().rstrip(".")], int(g[1])) if name == "monthday" else (MONTHS[g[1].lower()], int(g[0]))
            d = _safe(held_on.year, mon, day)
            if d and d < held_on:
                d = _safe(held_on.year + 1, mon, day)
            return d, raw
        if name == "nextweekday":
            monday_next = held_on - timedelta(days=held_on.weekday()) + timedelta(days=7)
            return monday_next + timedelta(days=WEEKDAYS[g[0].lower()]), raw
        if name == "inN":
            n = int(g[0]) if g[0].isdigit() else NUMWORDS[g[0].lower()]
            unit = g[1].lower()
            if unit.startswith("business"):
                d, left = held_on, n
                while left:
                    d += timedelta(days=1)
                    left -= d.weekday() < 5
                return d, raw
            return held_on + timedelta(days=n * (7 if unit.startswith("week") else 1)), raw
        if name == "eow":
            return _friday_of_week(held_on), raw
        if name == "eom":
            return date(held_on.year, held_on.month, calendar.monthrange(held_on.year, held_on.month)[1]), raw
        if name == "nextweek":
            return _friday_of_week(held_on - timedelta(days=held_on.weekday()) + timedelta(days=7)), raw
        if name == "tomorrow":
            return held_on + timedelta(days=1), raw
        if name == "today":
            return held_on, raw
        if name in {"ordinal", "ordinalword"}:
            day = int(g[0]) if name == "ordinal" else ORDINAL_WORDS[g[0].lower()]
            d = _safe(held_on.year, held_on.month, day)
            if d is None or d <= held_on:
                ny, nm = (held_on.year + (held_on.month == 12), held_on.month % 12 + 1)
                d = _safe(ny, nm, day)
            return d, raw
        if name == "weekday":
            return _next_weekday(held_on, WEEKDAYS[g[0].lower()]), raw
    v = VAGUE.search(text)
    return (None, v.group(0)) if v else (None, "")
