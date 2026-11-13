"""Edge cases for the recurrence period walk (Design 5.4).

Rules are written as RRULE text and parsed with ``parse_rrule`` so each test
reads like the calendar line it models. All datetimes are naive source wall
times; ``UNTIL`` is passed to ``expand`` already in that form.

Validates: Requirements 2.6, 6.3, 6.4, 6.5
"""

from datetime import date, datetime

import pytest

from app.ics.recurrence import ExpansionBudget, expand
from app.ics.types import InvalidCalendarError
from app.ics.values import parse_rrule

LO = datetime(1990, 1, 1)
HI = datetime(2040, 1, 1)


def _expand(rrule, dtstart, lo=LO, hi=HI, until=None, budget=None):
    return list(expand(parse_rrule(rrule), dtstart, lo, hi, until=until, budget=budget))


def test_weekly_byday_with_dtstart_on_wednesday():
    got = _expand("FREQ=WEEKLY;BYDAY=MO,WE,FR;COUNT=5", datetime(2026, 1, 7, 9))
    assert got == [
        datetime(2026, 1, 7, 9),
        datetime(2026, 1, 9, 9),
        datetime(2026, 1, 12, 9),
        datetime(2026, 1, 14, 9),
        datetime(2026, 1, 16, 9),
    ]


def test_weekly_without_byday_uses_dtstart_weekday():
    got = _expand("FREQ=WEEKLY;COUNT=3", datetime(2026, 1, 7, 9))
    assert got == [datetime(2026, 1, 7, 9), datetime(2026, 1, 14, 9), datetime(2026, 1, 21, 9)]


def test_monthly_bymonthday_31_skips_short_months():
    got = _expand("FREQ=MONTHLY;BYMONTHDAY=31", datetime(2026, 1, 31, 18), hi=datetime(2026, 12, 31, 23))
    assert [d.month for d in got] == [1, 3, 5, 7, 8, 10, 12]


def test_monthly_default_day_31_skips_short_months():
    got = _expand("FREQ=MONTHLY;COUNT=3", datetime(2026, 1, 31, 18))
    assert got == [datetime(2026, 1, 31, 18), datetime(2026, 3, 31, 18), datetime(2026, 5, 31, 18)]


def test_monthly_bymonthday_minus_one_is_last_day():
    got = _expand("FREQ=MONTHLY;BYMONTHDAY=-1;COUNT=5", datetime(2027, 12, 31, 8))
    assert got == [
        datetime(2027, 12, 31, 8),
        datetime(2028, 1, 31, 8),
        datetime(2028, 2, 29, 8),
        datetime(2028, 3, 31, 8),
        datetime(2028, 4, 30, 8),
    ]


def test_monthly_byday_last_friday():
    got = _expand("FREQ=MONTHLY;BYDAY=-1FR;COUNT=4", datetime(2026, 1, 30, 16))
    assert got == [
        datetime(2026, 1, 30, 16),
        datetime(2026, 2, 27, 16),
        datetime(2026, 3, 27, 16),
        datetime(2026, 4, 24, 16),
    ]


def test_monthly_byday_and_bymonthday_intersect():
    # Friday the 13th (RFC 5545 example), starting from a matching DTSTART.
    got = _expand("FREQ=MONTHLY;BYDAY=FR;BYMONTHDAY=13;COUNT=3", datetime(2026, 2, 13, 9))
    assert got == [datetime(2026, 2, 13, 9), datetime(2026, 3, 13, 9), datetime(2026, 11, 13, 9)]


def test_monthly_mixed_byday_is_union_of_plain_and_ordinal():
    # RFC 5545: BYDAY=MO,2TU is every Monday plus the second Tuesday (a union).
    # March 2026: 1 Mar is a Sunday, so Mondays are 2, 9, 16, 23, 30 and
    # Tuesdays are 3, 10, 17, 24, 31; the second Tuesday is 10 Mar.
    got = _expand(
        "FREQ=MONTHLY;BYDAY=MO,2TU",
        datetime(2026, 3, 2, 9),
        lo=datetime(2026, 3, 1),
        hi=datetime(2026, 3, 31, 23, 59),
    )
    assert got == [
        datetime(2026, 3, 2, 9),
        datetime(2026, 3, 9, 9),
        datetime(2026, 3, 10, 9),
        datetime(2026, 3, 16, 9),
        datetime(2026, 3, 23, 9),
        datetime(2026, 3, 30, 9),
    ]


def test_yearly_feb_29_only_in_leap_years():
    got = _expand("FREQ=YEARLY", datetime(2024, 2, 29, 10), hi=datetime(2033, 12, 31))
    assert got == [datetime(2024, 2, 29, 10), datetime(2028, 2, 29, 10), datetime(2032, 2, 29, 10)]


def test_yearly_bymonth_uses_dtstart_day():
    got = _expand("FREQ=YEARLY;BYMONTH=3,6;COUNT=4", datetime(2026, 3, 10, 9))
    assert got == [
        datetime(2026, 3, 10, 9),
        datetime(2026, 6, 10, 9),
        datetime(2027, 3, 10, 9),
        datetime(2027, 6, 10, 9),
    ]


def test_yearly_byday_ordinal_counts_within_year():
    # 20th Monday of the year (RFC 5545 example): 1997-05-19, 1998-05-18.
    got = _expand("FREQ=YEARLY;BYDAY=20MO;COUNT=3", datetime(1997, 5, 19, 9))
    assert got == [datetime(1997, 5, 19, 9), datetime(1998, 5, 18, 9), datetime(1999, 5, 17, 9)]


@pytest.mark.parametrize(
    ("wkst", "expected_days"),
    [
        # RFC 5545 3.8.5.3: WKST changes which weeks INTERVAL=2 selects.
        ("MO", [(8, 5), (8, 10), (8, 19), (8, 24)]),
        ("SU", [(8, 5), (8, 17), (8, 19), (8, 31)]),
    ],
)
def test_weekly_interval_two_depends_on_wkst(wkst, expected_days):
    got = _expand(f"FREQ=WEEKLY;INTERVAL=2;COUNT=4;BYDAY=TU,SU;WKST={wkst}", datetime(1997, 8, 5, 9))
    assert got == [datetime(1997, m, d, 9) for m, d in expected_days]


def test_count_includes_non_matching_dtstart():
    # DTSTART is a Tuesday but the rule only matches Mondays: DTSTART still counts.
    got = _expand("FREQ=WEEKLY;BYDAY=MO;COUNT=3", datetime(2026, 1, 6, 9))
    assert got == [datetime(2026, 1, 6, 9), datetime(2026, 1, 12, 9), datetime(2026, 1, 19, 9)]


def test_count_one_yields_only_dtstart():
    assert _expand("FREQ=DAILY;COUNT=1", datetime(2026, 1, 6, 9)) == [datetime(2026, 1, 6, 9)]


def test_until_exactly_on_an_occurrence_is_included():
    dtstart = datetime(2026, 1, 1, 9)
    rule = "FREQ=DAILY;UNTIL=20260105T090000"
    assert _expand(rule, dtstart, until=datetime(2026, 1, 5, 9)) == [
        datetime(2026, 1, day, 9) for day in range(1, 6)
    ]
    assert _expand(rule, dtstart, until=datetime(2026, 1, 5, 8, 59, 59)) == [
        datetime(2026, 1, day, 9) for day in range(1, 5)
    ]


def test_daily_filters_by_byday_and_bymonth():
    got = _expand("FREQ=DAILY;BYDAY=SA,SU;BYMONTH=2", datetime(2026, 1, 31, 10), hi=datetime(2026, 3, 31))
    assert got == [datetime(2026, 1, 31, 10)] + [
        datetime(2026, 2, day, 10) for day in (1, 7, 8, 14, 15, 21, 22, 28)
    ]


def test_results_are_limited_to_lo_hi_but_count_includes_earlier_dates():
    got = _expand(
        "FREQ=DAILY;COUNT=10",
        datetime(2026, 1, 1, 9),
        lo=datetime(2026, 1, 5),
        hi=datetime(2026, 1, 7, 9),
    )
    assert got == [datetime(2026, 1, 5, 9), datetime(2026, 1, 6, 9), datetime(2026, 1, 7, 9)]


def test_walk_stops_when_period_starts_after_hi():
    budget = ExpansionBudget()
    got = _expand("FREQ=DAILY", datetime(2026, 1, 1, 9), hi=datetime(2026, 1, 10, 23), budget=budget)
    assert len(got) == 10
    # Ten examined days at 1 + 1 each; the eleventh day starts after hi and is not examined.
    assert budget.examined == 20


def test_rule_until_requires_converted_until():
    with pytest.raises(ValueError):
        _expand("FREQ=DAILY;UNTIL=20260105T090000Z", datetime(2026, 1, 1, 9))


def test_aware_datetimes_are_rejected():
    from datetime import timezone

    with pytest.raises(ValueError):
        _expand("FREQ=DAILY;COUNT=2", datetime(2026, 1, 1, 9, tzinfo=timezone.utc))


# --- Examined-date budget, RDATE, and EXDATE (task 5.4) ----------------------
# Validates: Requirements 2.6, 6.5; Design 5.4, 5.5

FAR_HI = datetime(9999, 12, 31, 23, 59)
BUDGET_MESSAGE = (
    "Recurring events in this file need too much work to expand; the limit is 200,000 dates."
)


def test_never_matching_daily_count_rule_is_stopped_by_the_budget():
    # Feb 30 never exists, so COUNT=5 is never reached; without the budget the
    # walk would step through every day up to year 9999 (about 2.9 million).
    budget = ExpansionBudget()
    with pytest.raises(InvalidCalendarError) as caught:
        _expand(
            "FREQ=DAILY;BYMONTH=2;BYMONTHDAY=30;COUNT=5",
            datetime(1990, 1, 1, 9),
            hi=FAR_HI,
            budget=budget,
        )
    assert caught.value.issue == BUDGET_MESSAGE
    # Each examined day has no candidates and costs 1; the walk stops on the first date over.
    assert budget.examined == 200_001


def test_never_matching_daily_count_rule_with_window_hi_stops_at_hi():
    budget = ExpansionBudget()
    got = _expand(
        "FREQ=DAILY;BYMONTH=2;BYMONTHDAY=30;COUNT=5",
        datetime(1990, 1, 1, 9),
        hi=datetime(2027, 5, 1),
        budget=budget,
    )
    assert got == [datetime(1990, 1, 1, 9)]  # DTSTART is always the first occurrence
    assert budget.examined == (date(2027, 5, 1) - date(1990, 1, 1)).days + 1


def test_never_matching_monthly_rules_exhaust_a_shared_budget():
    # The first Monday is always day 1-7, so it is never the 20th.
    rule = "FREQ=MONTHLY;BYDAY=1MO;BYMONTHDAY=20;COUNT=5"
    budget = ExpansionBudget()
    months_to_9999 = (9999 - 1990 + 1) * 12
    for _ in range(2):
        _expand(rule, datetime(1990, 1, 1, 9), hi=FAR_HI, budget=budget)
    assert budget.examined == 2 * months_to_9999
    with pytest.raises(InvalidCalendarError) as caught:
        _expand(rule, datetime(1990, 1, 1, 9), hi=FAR_HI, budget=budget)
    assert caught.value.issue == BUDGET_MESSAGE
    assert budget.examined == 200_001


def test_daily_count_series_from_1990_fits_within_the_budget():
    budget = ExpansionBudget()
    lo, hi = datetime(2026, 10, 27), datetime(2027, 4, 27, 23, 59)
    got = _expand("FREQ=DAILY;COUNT=20000", datetime(1990, 1, 1, 9), lo=lo, hi=hi, budget=budget)
    assert got[0] == datetime(2026, 10, 27, 9)
    assert got[-1] == datetime(2027, 4, 27, 9)
    assert len(got) == (date(2027, 4, 27) - date(2026, 10, 27)).days + 1
    # COUNT rules walk from DTSTART: one day plus one candidate per period.
    assert budget.examined == 2 * ((date(2027, 4, 27) - date(1990, 1, 1)).days + 1)
    assert budget.examined < 200_000


def test_budget_limit_is_configurable():
    budget = ExpansionBudget(limit=10)
    with pytest.raises(InvalidCalendarError) as caught:
        _expand("FREQ=DAILY", datetime(2026, 1, 1, 9), hi=datetime(2026, 2, 1), budget=budget)
    assert "the limit is 10 dates" in caught.value.issue
    assert budget.examined == 12  # 2 per day; the sixth day goes over


WEEKLY_LO = datetime(2026, 1, 1)
WEEKLY_HI = datetime(2026, 1, 31, 23, 59)
WEEKLY_START = datetime(2026, 1, 5, 9)  # a Monday


def _weekly(**kwargs):
    return list(
        expand(parse_rrule("FREQ=WEEKLY;COUNT=4"), WEEKLY_START, WEEKLY_LO, WEEKLY_HI, **kwargs)
    )


def test_rdates_are_merged_deduplicated_sorted_and_charged():
    budget = ExpansionBudget()
    got = _weekly(
        budget=budget,
        rdates=[
            datetime(2026, 1, 21, 14),  # extra date between occurrences
            datetime(2026, 1, 12, 9),  # same as an RRULE occurrence
            datetime(2026, 1, 3, 9),  # before DTSTART but in [lo, hi]
            datetime(2026, 2, 10, 9),  # after hi
        ],
    )
    assert got == [
        datetime(2026, 1, 3, 9),
        datetime(2026, 1, 5, 9),
        datetime(2026, 1, 12, 9),
        datetime(2026, 1, 19, 9),
        datetime(2026, 1, 21, 14),
        datetime(2026, 1, 26, 9),
    ]
    # Four RDATEs at 1 each, plus four weekly periods at 1 + 1 each.
    assert budget.examined == 4 + 4 * 2


def test_rdates_count_toward_the_budget():
    budget = ExpansionBudget(limit=3)
    with pytest.raises(InvalidCalendarError):
        _weekly(budget=budget, rdates=[datetime(2026, 1, day, 9) for day in (6, 7, 8, 9)])
    assert budget.examined == 4


def test_datetime_exdate_removes_only_the_exact_wall_time():
    got = _weekly(exdates=[datetime(2026, 1, 12, 9), datetime(2026, 1, 19, 10)])
    # 19 Jan at 10:00 matches nothing; the excluded 12 Jan still counts toward COUNT=4.
    assert got == [datetime(2026, 1, 5, 9), datetime(2026, 1, 19, 9), datetime(2026, 1, 26, 9)]


def test_date_exdate_removes_every_original_on_that_day():
    got = _weekly(
        rdates=[datetime(2026, 1, 19, 15), datetime(2026, 1, 20, 9)],
        exdates=[date(2026, 1, 19)],
    )
    assert got == [
        datetime(2026, 1, 5, 9),
        datetime(2026, 1, 12, 9),
        datetime(2026, 1, 20, 9),
        datetime(2026, 1, 26, 9),
    ]


def test_exdate_can_remove_dtstart():
    assert _weekly(exdates=[WEEKLY_START]) == [
        datetime(2026, 1, 12, 9),
        datetime(2026, 1, 19, 9),
        datetime(2026, 1, 26, 9),
    ]
