"""Recurrence expansion for the supported ``RRULE`` subset (Design 5.4).

``expand`` walks recurrence periods in the series' source wall time (naive
datetimes), so a 09:00 class stays at 09:00 in its own zone across DST changes
(Requirement 6.3). Converting results to the upload zone is the event
pipeline's job.

The walk follows RFC 5545 3.3.10 for the parts in ``RuleSpec``:

- Defaults come from ``DTSTART``: the weekday for ``WEEKLY``, the day of the
  month for ``MONTHLY``, and the month and day for ``YEARLY``. The time of day
  always comes from ``DTSTART``.
- Period ``p`` is ``p`` days, weeks (starting on ``WKST``), months, or years
  after the period containing ``DTSTART``; only multiples of ``INTERVAL`` are
  examined.
- ``DTSTART`` is always the first occurrence and counts toward ``COUNT``, even
  when it does not match the rule.
- ``UNTIL`` is inclusive.
- Rules without ``COUNT`` start at the period containing ``lo`` (aligned to
  ``INTERVAL``); ``COUNT`` rules start at ``DTSTART``'s period.
- The walk stops when a period starts after ``hi`` or after ``UNTIL``.
- ``RDATE`` starts are merged in and ``EXDATE`` starts removed; the result is
  de-duplicated and sorted.
- A file-wide ``ExpansionBudget`` bounds the work: every examined period and
  every ``RDATE`` is charged as it is examined, and going over the limit
  raises ``InvalidCalendarError`` (Requirement 2.6; Design 5.5).

Standard library only (Requirement 12.1).
"""

import calendar
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.ics.types import InvalidCalendarError
from app.ics.values import Frequency, RuleSpec, WeekdayNum

_MIN_ORDINAL = date.min.toordinal()
_MAX_ORDINAL = date.max.toordinal()


@dataclass
class ExpansionBudget:
    """File-wide count of examined candidate dates, shared across ``expand`` calls.

    Each examined period costs ``1 + len(candidates)`` and each ``RDATE`` costs
    1 (Design 5.4). The event pipeline creates one budget per file with
    ``limit=ImportLimits.max_examined_dates`` and passes it to every series, so
    the limit bounds the whole file rather than each series.
    """

    limit: int = 200_000
    examined: int = 0

    def charge(self, dates: int) -> None:
        """Add ``dates`` to the count; raise once the count is over ``limit``."""
        self.examined += dates
        if self.examined > self.limit:
            raise InvalidCalendarError(
                "Recurring events in this file need too much work to expand; "
                f"the limit is {self.limit:,} dates."
            )


def expand(
    rule: RuleSpec,
    dtstart: datetime,
    lo: datetime,
    hi: datetime,
    until: datetime | None = None,
    budget: ExpansionBudget | None = None,
    rdates: Iterable[datetime] = (),
    exdates: Iterable[date] = (),
) -> tuple[datetime, ...]:
    """Return the sorted, de-duplicated original starts of the series in ``[lo, hi]``.

    All datetimes are naive source wall times. ``until`` is the rule's
    ``UNTIL`` already converted to source wall time by the caller (Design 5.4);
    it is required whenever ``rule.until`` is set, because the file form in
    ``rule.until`` cannot be interpreted without the series' zone.

    Rules without ``COUNT`` start at the period containing ``lo`` (rounded
    down to a multiple of ``INTERVAL``), so old series cost the same as new
    ones. ``COUNT`` rules start at ``DTSTART``'s period, because ``COUNT``
    counts from there (Design 5.4).

    ``rdates`` are extra ``RDATE`` starts; they are added as written, without
    regard to ``COUNT`` or ``UNTIL``, which apply to the rule only (RFC 5545
    3.8.5.2). ``exdates`` remove originals: a ``datetime`` removes the original
    with exactly that wall time, and a plain ``date`` (a DATE ``EXDATE``)
    removes every original on that day. Exclusions apply after ``COUNT``, so
    an excluded date still counts toward it.

    Raises ``InvalidCalendarError`` when ``budget`` goes over its limit.
    """
    rdates = tuple(rdates)
    exdates = tuple(exdates)
    for value in rdates:
        if value.tzinfo is not None:
            raise ValueError("rdates must be naive source wall times.")
    for value in exdates:
        if isinstance(value, datetime) and value.tzinfo is not None:
            raise ValueError("exdates must be naive source wall times.")
    if budget is not None and rdates:
        budget.charge(len(rdates))

    starts = _walk(rule, dtstart, lo, hi, until, budget, from_window=True)[0]
    if not rdates and not exdates:
        return starts

    excluded_times = {value for value in exdates if isinstance(value, datetime)}
    excluded_days = {value for value in exdates if not isinstance(value, datetime)}
    merged = set(starts)
    merged.update(value for value in rdates if lo <= value <= hi)
    return tuple(
        sorted(
            value
            for value in merged
            if value not in excluded_times and value.date() not in excluded_days
        )
    )


def _walk(
    rule: RuleSpec,
    dtstart: datetime,
    lo: datetime,
    hi: datetime,
    until: datetime | None,
    budget: ExpansionBudget | None,
    *,
    from_window: bool,
) -> tuple[tuple[datetime, ...], int]:
    """``expand``'s walk; also returns the number of periods examined.

    ``from_window=False`` forces the walk to start at period 0 whatever the
    rule. Only tests use that and the period count (Property 10).
    """
    for name, value in (("dtstart", dtstart), ("lo", lo), ("hi", hi), ("until", until)):
        if value is not None and value.tzinfo is not None:
            raise ValueError(f"{name} must be a naive source wall time.")
    if rule.until is not None and until is None:
        raise ValueError("until must be given, in source wall time, when the rule has UNTIL.")

    results: list[datetime] = []
    periods = 0
    # DTSTART is the first occurrence and counts toward COUNT (RFC 5545 3.3.10).
    # When the walk starts later, DTSTART lies in an earlier period, so before lo.
    if lo <= dtstart <= hi:
        results.append(dtstart)
    counted = 1
    if rule.count is not None and counted >= rule.count:
        return tuple(results), periods

    walker = _PeriodWalker(rule, dtstart)
    clock = dtstart.time()
    p = walker.first_period(lo) if from_window and rule.count is None else 0
    while True:
        start = walker.period_start(p)
        if start is None:  # past date.max
            break
        period_start = datetime.combine(start, time.min)
        if period_start > hi or (until is not None and period_start > until):
            break
        candidates = sorted(walker.candidates(p))
        periods += 1
        if budget is not None:
            budget.charge(1 + len(candidates))
        for day in candidates:
            occurrence = datetime.combine(day, clock)
            if occurrence <= dtstart:  # before DTSTART, or DTSTART itself (already counted)
                continue
            if until is not None and occurrence > until:
                return tuple(results), periods
            if occurrence > hi:
                return tuple(results), periods
            counted += 1
            if occurrence >= lo:
                results.append(occurrence)
            if rule.count is not None and counted >= rule.count:
                return tuple(results), periods
        p += rule.interval
    return tuple(results), periods


class _PeriodWalker:
    """Period starts and candidate dates for one rule and ``DTSTART``."""

    def __init__(self, rule: RuleSpec, dtstart: datetime) -> None:
        self.rule = rule
        self.dtstart = dtstart
        first = dtstart.date()
        self.day0 = first.toordinal()
        self.week0 = self.day0 - (first.weekday() - rule.wkst) % 7
        self.month0 = first.year * 12 + (first.month - 1)
        self.year0 = first.year
        self.weekdays = frozenset(item.weekday for item in rule.byday)

    # --- Periods -------------------------------------------------------------

    def first_period(self, lo: datetime) -> int:
        """Largest multiple of ``INTERVAL`` at or before ``lo``'s period, never below 0.

        Candidates of a period lie inside it, so every period before the one
        containing ``lo`` holds only dates before ``lo`` (Design 5.4).
        """
        freq = self.rule.freq
        day = lo.date()
        if freq is Frequency.DAILY:
            index = day.toordinal() - self.day0
        elif freq is Frequency.WEEKLY:
            index = (day.toordinal() - self.week0) // 7
        elif freq is Frequency.MONTHLY:
            index = day.year * 12 + (day.month - 1) - self.month0
        else:
            index = day.year - self.year0
        if index <= 0:
            return 0
        return index - index % self.rule.interval

    def period_start(self, p: int) -> date | None:
        """First day of period ``p``, or ``None`` when it is past ``date.max``."""
        freq = self.rule.freq
        if freq is Frequency.DAILY:
            return _from_ordinal(self.day0 + p)
        if freq is Frequency.WEEKLY:
            # The first week may start before date.min; its first valid day stands in.
            return _from_ordinal(max(self.week0 + 7 * p, _MIN_ORDINAL))
        if freq is Frequency.MONTHLY:
            year, month0 = divmod(self.month0 + p, 12)
            return date(year, month0 + 1, 1) if year <= date.max.year else None
        year = self.year0 + p
        return date(year, 1, 1) if year <= date.max.year else None

    # --- Candidates ----------------------------------------------------------

    def candidates(self, p: int) -> set[date]:
        freq = self.rule.freq
        if freq is Frequency.DAILY:
            return self._daily(p)
        if freq is Frequency.WEEKLY:
            return self._weekly(p)
        if freq is Frequency.MONTHLY:
            year, month0 = divmod(self.month0 + p, 12)
            return self._monthly(year, month0 + 1)
        return self._yearly(self.year0 + p)

    def _daily(self, p: int) -> set[date]:
        day = _from_ordinal(self.day0 + p)
        rule = self.rule
        if day is None:
            return set()
        if rule.bymonth and day.month not in rule.bymonth:
            return set()
        if rule.bymonthday and day not in _monthdays(day.year, day.month, rule.bymonthday):
            return set()
        if self.weekdays and day.weekday() not in self.weekdays:
            return set()
        return {day}

    def _weekly(self, p: int) -> set[date]:
        rule = self.rule
        weekdays = self.weekdays or {self.dtstart.weekday()}
        start = self.week0 + 7 * p
        days = set()
        for weekday in weekdays:
            day = _from_ordinal(start + (weekday - rule.wkst) % 7)
            if day is not None and (not rule.bymonth or day.month in rule.bymonth):
                days.add(day)
        return days

    def _monthly(self, year: int, month: int) -> set[date]:
        rule = self.rule
        if rule.bymonth and month not in rule.bymonth:
            return set()
        if rule.bymonthday:
            days = _monthdays(year, month, rule.bymonthday)
            if rule.byday:
                days &= _month_bydays(year, month, rule.byday)
            return days
        if rule.byday:
            return _month_bydays(year, month, rule.byday)
        return _valid_days(year, month, (self.dtstart.day,))

    def _yearly(self, year: int) -> set[date]:
        rule = self.rule
        if not rule.bymonthday and not rule.byday:
            months = rule.bymonth or (self.dtstart.month,)
            days: set[date] = set()
            for month in months:
                days |= _valid_days(year, month, (self.dtstart.day,))
            return days
        # BYMONTHDAY and BYDAY expand over BYMONTH's months, or the whole year.
        months = rule.bymonth or tuple(range(1, 13))

        def bydays() -> set[date]:
            if rule.bymonth:  # ordinals count within each month
                found: set[date] = set()
                for month in months:
                    found |= _month_bydays(year, month, rule.byday)
                return found
            return _frame_bydays(date(year, 1, 1), date(year, 12, 31), rule.byday)

        if rule.bymonthday:
            days = set()
            for month in months:
                days |= _monthdays(year, month, rule.bymonthday)
            if rule.byday:
                days &= bydays()
            return days
        return bydays()


# --- Helpers -----------------------------------------------------------------


def _from_ordinal(ordinal: int) -> date | None:
    if _MIN_ORDINAL <= ordinal <= _MAX_ORDINAL:
        return date.fromordinal(ordinal)
    return None


def _valid_days(year: int, month: int, days: tuple[int, ...]) -> set[date]:
    """The given days of the month, dropping ones the month doesn't have (e.g. April 31)."""
    length = calendar.monthrange(year, month)[1]
    return {date(year, month, day) for day in days if 1 <= day <= length}


def _monthdays(year: int, month: int, bymonthday: tuple[int, ...]) -> set[date]:
    """``BYMONTHDAY`` days in a month; negative values count back from the month end."""
    length = calendar.monthrange(year, month)[1]
    resolved = tuple(day if day > 0 else length + 1 + day for day in bymonthday)
    return _valid_days(year, month, resolved)


def _month_bydays(year: int, month: int, byday: tuple[WeekdayNum, ...]) -> set[date]:
    length = calendar.monthrange(year, month)[1]
    return _frame_bydays(date(year, month, 1), date(year, month, length), byday)


def _frame_bydays(first: date, last: date, byday: tuple[WeekdayNum, ...]) -> set[date]:
    """``BYDAY`` days within ``[first, last]``; an ordinal picks the nth (or nth-from-last)."""
    days: set[date] = set()
    span = (last - first).days
    for item in byday:
        offset = (item.weekday - first.weekday()) % 7
        matches = [first + timedelta(days=d) for d in range(offset, span + 1, 7)]
        if item.ordinal is None:
            days.update(matches)
        elif item.ordinal > 0 and item.ordinal <= len(matches):
            days.add(matches[item.ordinal - 1])
        elif item.ordinal < 0 and -item.ordinal <= len(matches):
            days.add(matches[item.ordinal])
    return days
