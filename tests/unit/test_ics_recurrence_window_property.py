"""Property test: starting the recurrence walk at the import window changes nothing.

Feature: calendar-import, Property 10: Starting at the window changes nothing
Validates: Requirements 6.1, 6.2; Design 5.4

For rules without ``COUNT``, ``expand`` starts at the period containing ``lo``
(rounded down to a multiple of ``INTERVAL``) instead of at ``DTSTART``'s
period. The reference is the same walk forced to start at period 0, run from
``DTSTART`` and filtered to ``[lo, hi]`` here. The test also checks that the
windowed walk examines no more periods than fit between ``lo`` and ``hi``.

The reference is the expander itself, not ``dateutil``, so any supported rule
can be generated: ``BYMONTHDAY`` over the full +-1..31 range, mixed plain and
ordinal ``BYDAY``, intervals that don't divide 7 or 12, and rules that never
match.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from hypothesis import example, given, settings, strategies as st

from app.ics.recurrence import _walk, expand
from app.ics.values import WEEKDAYS, parse_rrule

_WEEKDAY_NAMES = {number: name for name, number in WEEKDAYS.items()}
_FREQS = ("DAILY", "WEEKLY", "MONTHLY", "YEARLY")
# Shortest length of each period, used for the bound on periods examined.
_SHORTEST_PERIOD = {
    "DAILY": timedelta(days=1),
    "WEEKLY": timedelta(days=7),
    "MONTHLY": timedelta(days=28),
    "YEARLY": timedelta(days=365),
}
_MONTHDAYS = tuple(range(1, 32)) + tuple(range(-31, 0))


@dataclass(frozen=True)
class Case:
    freq: str
    dtstart: datetime
    lo: datetime
    hi: datetime
    interval: int = 1
    until: datetime | None = None
    byday: tuple[tuple[int, int | None], ...] = ()  # (weekday, ordinal or None)
    bymonthday: tuple[int, ...] = ()
    bymonth: tuple[int, ...] = ()
    wkst: int = 0

    def rrule_text(self) -> str:
        parts = [f"FREQ={self.freq}", f"INTERVAL={self.interval}"]
        if self.until is not None:
            parts.append(f"UNTIL={self.until:%Y%m%dT%H%M%S}")
        if self.byday:
            items = (f"{'' if n is None else n}{_WEEKDAY_NAMES[wd]}" for wd, n in self.byday)
            parts.append("BYDAY=" + ",".join(items))
        if self.bymonthday:
            parts.append("BYMONTHDAY=" + ",".join(map(str, self.bymonthday)))
        if self.bymonth:
            parts.append("BYMONTH=" + ",".join(map(str, self.bymonth)))
        parts.append(f"WKST={_WEEKDAY_NAMES[self.wkst]}")
        return ";".join(parts)


@st.composite
def cases(draw):
    freq = draw(st.sampled_from(_FREQS))
    day = draw(st.dates(min_value=date(1995, 1, 1), max_value=date(2035, 12, 31)))
    dtstart = datetime.combine(day, draw(st.times()).replace(microsecond=0))
    interval = draw(st.integers(1, 3) | st.integers(1, 13))
    wkst = draw(st.integers(0, 6))

    bymonth = ()
    if draw(st.booleans()):
        bymonth = tuple(sorted(draw(st.lists(st.integers(1, 12), min_size=1, max_size=3, unique=True))))

    bymonthday = ()
    if freq != "WEEKLY" and draw(st.booleans()):
        bymonthday = tuple(draw(st.lists(st.sampled_from(_MONTHDAYS), min_size=1, max_size=3, unique=True)))

    byday = ()
    if draw(st.booleans()):
        weekdays = draw(st.lists(st.integers(0, 6), min_size=1, max_size=3, unique=True))
        if freq in ("MONTHLY", "YEARLY"):
            limit = 53 if freq == "YEARLY" and not bymonth else 5
            ordinal = st.none() | st.integers(1, limit) | st.integers(-limit, -1)
            byday = tuple((wd, draw(ordinal)) for wd in weekdays)  # plain, ordinal, or mixed
        else:
            byday = tuple((wd, None) for wd in weekdays)

    # The window starts anywhere from shortly before DTSTART to ~5 years after it.
    lo = dtstart + timedelta(
        days=draw(st.integers(-60, 5 * 366) | st.integers(5 * 365 - 60, 5 * 366)),
        seconds=draw(st.just(0) | st.integers(0, 86399)),
    )
    hi = lo + timedelta(
        days=draw(st.integers(0, 400) | st.just(184)),
        seconds=draw(st.just(0) | st.integers(0, 86399)),
    )

    until = None
    if draw(st.booleans()):
        until = dtstart + timedelta(days=draw(st.integers(0, 6 * 366)), seconds=draw(st.integers(0, 86399)))

    return Case(
        freq=freq,
        dtstart=dtstart,
        lo=lo,
        hi=hi,
        interval=interval,
        until=until,
        byday=byday,
        bymonthday=bymonthday,
        bymonth=bymonth,
        wkst=wkst,
    )


# Feature: calendar-import, Property 10: Starting at the window changes nothing
@settings(max_examples=300, deadline=None)
@given(cases())
@example(  # INTERVAL=2 weeks with WKST=SU; window years later starts mid-week
    Case(
        freq="WEEKLY",
        dtstart=datetime(1997, 8, 5, 9),
        lo=datetime(2001, 8, 8, 12),
        hi=datetime(2002, 2, 8, 12),
        interval=2,
        byday=((1, None), (6, None)),
        wkst=6,
    )
)
@example(  # same rule with WKST=MO selects different weeks
    Case(
        freq="WEEKLY",
        dtstart=datetime(1997, 8, 5, 9),
        lo=datetime(2001, 8, 8, 12),
        hi=datetime(2002, 2, 8, 12),
        interval=2,
        byday=((1, None), (6, None)),
        wkst=0,
    )
)
@example(  # INTERVAL=5 months, which doesn't divide a year, across year ends
    Case(
        freq="MONTHLY",
        dtstart=datetime(2021, 11, 30, 8),
        lo=datetime(2026, 3, 1),
        hi=datetime(2026, 12, 31),
        interval=5,
        bymonthday=(-1, 30),
    )
)
@example(  # every third year, Feb 29 only
    Case(
        freq="YEARLY",
        dtstart=datetime(2020, 2, 29, 10),
        lo=datetime(2024, 1, 1),
        hi=datetime(2033, 1, 1),
        interval=3,
        bymonth=(2,),
        bymonthday=(29,),
    )
)
@example(  # UNTIL inside the window
    Case(
        freq="DAILY",
        dtstart=datetime(2022, 1, 1, 9),
        lo=datetime(2026, 1, 1),
        hi=datetime(2026, 7, 1),
        interval=3,
        until=datetime(2026, 2, 1, 9),
    )
)
@example(  # UNTIL before the window: nothing
    Case(
        freq="WEEKLY",
        dtstart=datetime(2022, 1, 3, 9),
        lo=datetime(2026, 1, 1),
        hi=datetime(2026, 7, 1),
        until=datetime(2025, 12, 31, 23),
    )
)
@example(  # window starting before DTSTART keeps DTSTART first
    Case(
        freq="MONTHLY",
        dtstart=datetime(2026, 3, 4, 9),
        lo=datetime(2026, 1, 1),
        hi=datetime(2026, 7, 1),
        byday=((0, None), (1, 2)),
    )
)
def test_starting_at_the_window_changes_nothing(case):
    rule = parse_rrule(case.rrule_text())
    assert rule.count is None

    got, periods = _walk(rule, case.dtstart, case.lo, case.hi, case.until, None, from_window=True)

    full, _ = _walk(
        rule, case.dtstart, min(case.lo, case.dtstart), case.hi, case.until, None, from_window=False
    )
    expected = tuple(d for d in full if case.lo <= d <= case.hi)
    assert got == expected, case.rrule_text()
    assert expand(rule, case.dtstart, case.lo, case.hi, until=case.until) == got

    assert periods <= (case.hi - case.lo) / _SHORTEST_PERIOD[case.freq] + 2, (case.rrule_text(), periods)
