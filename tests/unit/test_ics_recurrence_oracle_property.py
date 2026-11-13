"""Property test: the recurrence expander agrees with ``dateutil.rrule``.

Feature: calendar-import, Property 9: Expander agrees with the reference
Validates: Requirements 6.3, 6.4, 6.5

``dateutil`` is the reference here and nowhere else: ``app/ics`` never imports
it (``test_ics_boundary.py``). Two adjustments bring it in line with RFC 5545:

- ``DTSTART`` is always the first occurrence and counts toward ``COUNT``.
  ``dateutil`` leaves out a ``DTSTART`` that doesn't match the rule, so the
  reference adds it and runs ``dateutil`` with ``COUNT - 1`` in that case.
- ``dateutil`` intersects plain ``BYDAY`` weekdays with ordinal ones, while
  RFC 5545 takes their union. A generated ``BYDAY`` is therefore either all
  plain or all ordinal, where both readings agree.

``dateutil`` checks ``UNTIL`` and the query end only when a date matches, so a
rule that never matches again scans to year 9999 (Design 5.1). The generators
only build rules that keep matching: ``BYMONTHDAY`` is limited to 1..28 and -1,
ordinal ``BYDAY`` is never combined with ``BYMONTHDAY``, ``DAILY`` intervals are
coprime with 7, ``MONTHLY`` intervals divide 12, ``BYMONTH`` always holds a
month the rule can reach and use, and ``YEARLY`` never asks for a 5th weekday
of February alone.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from dateutil import rrule as du
from hypothesis import example, given, settings, strategies as st

from app.ics.recurrence import ExpansionBudget, expand
from app.ics.values import WEEKDAYS, parse_rrule

_WEEKDAY_NAMES = {number: name for name, number in WEEKDAYS.items()}
_DU_FREQ = {"DAILY": du.DAILY, "WEEKLY": du.WEEKLY, "MONTHLY": du.MONTHLY, "YEARLY": du.YEARLY}
_INTERVALS = {"DAILY": (1, 2, 3), "WEEKLY": (1, 2, 3, 4), "MONTHLY": (1, 2, 3, 4, 6), "YEARLY": (1, 2, 3)}
_MONTHDAYS = tuple(range(1, 29)) + (-1,)


@dataclass(frozen=True)
class Case:
    freq: str
    dtstart: datetime
    lo: datetime
    hi: datetime
    interval: int = 1
    count: int | None = None
    until: datetime | None = None
    byday: tuple[tuple[int, int | None], ...] = ()  # (weekday, ordinal or None)
    bymonthday: tuple[int, ...] = ()
    bymonth: tuple[int, ...] = ()
    wkst: int = 0

    def rrule_text(self) -> str:
        parts = [f"FREQ={self.freq}", f"INTERVAL={self.interval}"]
        if self.count is not None:
            parts.append(f"COUNT={self.count}")
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


def _sorted_unique(items):
    return tuple(sorted(set(items)))


@st.composite
def cases(draw):
    freq = draw(st.sampled_from(sorted(_DU_FREQ)))
    day = draw(st.dates(min_value=date(1995, 1, 1), max_value=date(2035, 12, 31)))
    clock = draw(st.times()).replace(microsecond=0)
    dtstart = datetime.combine(day, clock)
    interval = draw(st.sampled_from(_INTERVALS[freq]))
    wkst = draw(st.integers(0, 6))

    bymonth = ()
    if draw(st.booleans()):
        bymonth = draw(st.lists(st.integers(1, 12), min_size=1, max_size=3))
        if freq == "MONTHLY" and interval > 1:
            # Only months dtstart.month + k * INTERVAL are examined; keep one in BYMONTH.
            k = draw(st.integers(0, 11))
            bymonth.append((dtstart.month - 1 + k * interval) % 12 + 1)
        bymonth = _sorted_unique(bymonth)

    bymonthday = ()
    if freq != "WEEKLY" and draw(st.booleans()):
        bymonthday = _sorted_unique(draw(st.lists(st.sampled_from(_MONTHDAYS), min_size=1, max_size=3)))

    byday = ()
    if draw(st.booleans()):
        ordinal_allowed = freq in ("MONTHLY", "YEARLY") and not bymonthday
        if ordinal_allowed and draw(st.booleans()):
            if freq == "YEARLY" and not bymonth:
                limit = 53
            elif freq == "YEARLY" and bymonth == (2,):
                # A 5th weekday in February needs a leap year, which INTERVAL=2 from an
                # odd year never reaches.
                limit = 4
            else:
                limit = 5
            ordinals = st.integers(1, limit) | st.integers(-limit, -1)
            byday = draw(
                st.lists(st.tuples(st.integers(0, 6), ordinals), min_size=1, max_size=2, unique=True)
            )
        else:
            byday = [(wd, None) for wd in draw(st.lists(st.integers(0, 6), min_size=1, max_size=3, unique=True))]
        byday = tuple(byday)

    if (
        freq in ("MONTHLY", "YEARLY")
        and bymonth
        and not bymonthday
        and not byday
        and dtstart.day > 28
    ):
        # The default day (DTSTART's) must exist in a BYMONTH month, or nothing ever matches.
        bymonth = _sorted_unique(bymonth + (dtstart.month,))

    count = until = None
    end = draw(st.sampled_from(("none", "count", "until")))
    if end == "count":
        count = draw(st.integers(1, 40))
    elif end == "until":
        offset = timedelta(days=draw(st.integers(0, 1500)), seconds=draw(st.just(0) | st.integers(-86399, 86399)))
        until = max(dtstart, dtstart + offset)

    # Favor windows near DTSTART, where COUNT and UNTIL series still have dates.
    lo_days = draw(st.integers(-60, 120) | st.integers(-60, 1500))
    lo = dtstart + timedelta(days=lo_days, seconds=draw(st.just(0) | st.integers(0, 86399)))
    hi = lo + timedelta(days=draw(st.integers(0, 800)), seconds=draw(st.just(0) | st.integers(0, 86399)))

    return Case(
        freq=freq,
        dtstart=dtstart,
        lo=lo,
        hi=hi,
        interval=interval,
        count=count,
        until=until,
        byday=byday,
        bymonthday=bymonthday,
        bymonth=bymonth,
        wkst=wkst,
    )


def _reference(case: Case) -> list[datetime]:
    """RFC 5545 occurrences in ``[lo, hi]``, computed with ``dateutil``."""

    def rule(count):
        return du.rrule(
            _DU_FREQ[case.freq],
            dtstart=case.dtstart,
            interval=case.interval,
            wkst=case.wkst,
            count=count,
            until=case.until,
            byweekday=[du.weekdays[wd](n) if n else du.weekdays[wd] for wd, n in case.byday] or None,
            bymonthday=case.bymonthday or None,
            bymonth=case.bymonth or None,
        )

    count = case.count
    if count is not None:
        dtstart_matches = next(iter(rule(1))) == case.dtstart
        if not dtstart_matches:
            count -= 1  # the non-matching DTSTART uses up one occurrence
    dates = set(rule(count).between(case.lo, case.hi, inc=True)) if count != 0 else set()
    if case.lo <= case.dtstart <= case.hi:
        dates.add(case.dtstart)
    return sorted(dates)


# Feature: calendar-import, Property 9: Expander agrees with the reference
@settings(max_examples=300, deadline=None)
@given(cases())
@example(  # RFC 5545 3.8.5.3: WKST=SU changes which weeks INTERVAL=2 selects
    Case(
        freq="WEEKLY",
        dtstart=datetime(1997, 8, 5, 9),
        lo=datetime(1997, 8, 1),
        hi=datetime(1997, 9, 30),
        interval=2,
        count=4,
        byday=((1, None), (6, None)),
        wkst=6,
    )
)
@example(  # non-matching DTSTART counts toward COUNT
    Case(
        freq="MONTHLY",
        dtstart=datetime(2026, 1, 6, 9),
        lo=datetime(2026, 1, 1),
        hi=datetime(2026, 12, 31),
        count=3,
        byday=((4, -1),),
    )
)
@example(  # UNTIL exactly on an occurrence
    Case(
        freq="DAILY",
        dtstart=datetime(2026, 1, 1, 9),
        lo=datetime(2025, 12, 1),
        hi=datetime(2026, 2, 1),
        until=datetime(2026, 1, 5, 9),
    )
)
def test_expander_agrees_with_dateutil(case):
    rule = parse_rrule(case.rrule_text())
    got = expand(rule, case.dtstart, case.lo, case.hi, until=case.until, budget=ExpansionBudget())
    assert list(got) == _reference(case), case.rrule_text()
