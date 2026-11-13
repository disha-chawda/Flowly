"""Unit tests for RRULE parsing and validation (Design 4.3, 5.2).

One example per row of the Design 5.2 table that the value parser decides,
plus the BYDAY ordinal ranges. The event-level rows (more than one RRULE,
RDATE;VALUE=PERIOD, RANGE=THISANDFUTURE) are covered with the event pipeline.

Validates: Requirements 6.4, 6.10, 8.7
"""

from datetime import date, datetime

import pytest

from app.ics.values import (
    DateTimeValue,
    Frequency,
    RuleSpec,
    UnsupportedRuleError,
    ValueParseError,
    WeekdayNum,
    parse_rrule,
)

# --- Valid rules -------------------------------------------------------------


def test_minimal_rule_uses_defaults():
    assert parse_rrule("FREQ=DAILY") == RuleSpec(freq=Frequency.DAILY)


def test_all_supported_parts():
    rule = parse_rrule(
        "FREQ=MONTHLY;INTERVAL=2;UNTIL=20270101T000000Z;BYDAY=MO,-1FR,+2TU;"
        "BYMONTHDAY=1,-1;BYMONTH=1,12;WKST=SU"
    )
    assert rule == RuleSpec(
        freq=Frequency.MONTHLY,
        interval=2,
        until=DateTimeValue(datetime(2027, 1, 1), utc=True),
        byday=(WeekdayNum(0), WeekdayNum(4, -1), WeekdayNum(1, 2)),
        bymonthday=(1, -1),
        bymonth=(1, 12),
        wkst=6,
    )


def test_count_and_date_until():
    assert parse_rrule("FREQ=WEEKLY;COUNT=10").count == 10
    assert parse_rrule("FREQ=WEEKLY;UNTIL=20261231").until == date(2026, 12, 31)


def test_names_and_enumerated_values_are_case_insensitive():
    assert parse_rrule("freq=weekly;byday=mo,We;wkst=su") == parse_rrule(
        "FREQ=WEEKLY;BYDAY=MO,WE;WKST=SU"
    )


def test_part_order_does_not_matter():
    assert parse_rrule("BYDAY=MO;FREQ=WEEKLY") == parse_rrule("FREQ=WEEKLY;BYDAY=MO")


def test_rule_spec_is_frozen():
    rule = parse_rrule("FREQ=DAILY")
    with pytest.raises(AttributeError):
        rule.interval = 2  # type: ignore[misc]


# --- Malformed (Design 5.2 row 1) ------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        # Syntax errors
        "",
        "FREQ",
        "FREQ=",
        "FREQ=DAILY;",
        "FREQ=DAILY;;COUNT=2",
        "=DAILY",
        "FREQ DAILY",
        "FREQ=DAILY;BY DAY=MO",
        # Repeated part
        "FREQ=DAILY;COUNT=2;COUNT=3",
        "FREQ=DAILY;interval=2;INTERVAL=2",
        # Missing FREQ
        "COUNT=5",
        # COUNT together with UNTIL
        "FREQ=DAILY;COUNT=5;UNTIL=20261231T000000Z",
        # INTERVAL < 1, COUNT < 1, non-numbers
        "FREQ=DAILY;INTERVAL=0",
        "FREQ=DAILY;INTERVAL=-1",
        "FREQ=DAILY;COUNT=0",
        "FREQ=DAILY;COUNT=two",
        "FREQ=DAILY;COUNT=" + "9" * 5000,
        # Bad UNTIL
        "FREQ=DAILY;UNTIL=20260230T000000Z",
        "FREQ=DAILY;UNTIL=tomorrow",
        # Out-of-range numbers
        "FREQ=MONTHLY;BYMONTHDAY=0",
        "FREQ=MONTHLY;BYMONTHDAY=32",
        "FREQ=MONTHLY;BYMONTHDAY=-32",
        "FREQ=YEARLY;BYMONTH=0",
        "FREQ=YEARLY;BYMONTH=13",
        "FREQ=YEARLY;BYMONTH=-1",
        "FREQ=YEARLY;BYDAY=0MO",
        "FREQ=YEARLY;BYDAY=54MO",
        "FREQ=YEARLY;BYDAY=-54MO",
        # Bad list items and weekdays
        "FREQ=WEEKLY;BYDAY=MO,,WE",
        "FREQ=WEEKLY;BYDAY=XX",
        "FREQ=WEEKLY;BYDAY=+MO",
        "FREQ=WEEKLY;WKST=XX",
        "FREQ=WEEKLY;WKST=1MO",
    ],
)
def test_malformed_rules(raw):
    with pytest.raises(ValueParseError):
        parse_rrule(raw)


# --- Unsupported (Design 5.2 rows 2 and 3) ----------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        # Other FREQ values
        "FREQ=HOURLY",
        "FREQ=MINUTELY",
        "FREQ=SECONDLY",
        "FREQ=FORTNIGHTLY",
        # Parts outside the supported set
        "FREQ=MONTHLY;BYDAY=MO;BYSETPOS=1",
        "FREQ=YEARLY;BYYEARDAY=100",
        "FREQ=YEARLY;BYWEEKNO=20",
        "FREQ=DAILY;BYHOUR=9",
        "FREQ=DAILY;BYMINUTE=30",
        "FREQ=DAILY;BYSECOND=0",
        "FREQ=DAILY;X-NAME=1",
        # Ordinal BYDAY with DAILY or WEEKLY
        "FREQ=DAILY;BYDAY=1MO",
        "FREQ=WEEKLY;BYDAY=-1FR",
        # BYMONTHDAY with WEEKLY
        "FREQ=WEEKLY;BYMONTHDAY=15",
    ],
)
def test_unsupported_rules(raw):
    with pytest.raises(UnsupportedRuleError):
        parse_rrule(raw)


def test_unsupported_is_not_a_value_parse_error():
    """The pipeline must be able to tell the two outcomes apart."""
    assert not issubclass(UnsupportedRuleError, ValueParseError)


def test_unsupported_freq_wins_over_bad_values_of_other_parts():
    with pytest.raises(UnsupportedRuleError):
        parse_rrule("FREQ=HOURLY;INTERVAL=0")


# --- BYDAY ordinal ranges -------------------------------------------------


@pytest.mark.parametrize("ordinal", [1, 5, -1, -5])
@pytest.mark.parametrize("prefix", ["FREQ=MONTHLY", "FREQ=YEARLY;BYMONTH=3"])
def test_month_ordinals_within_five_are_valid(prefix, ordinal):
    rule = parse_rrule(f"{prefix};BYDAY={ordinal}TH")
    assert rule.byday == (WeekdayNum(3, ordinal),)


@pytest.mark.parametrize("ordinal", [6, -6, 53, -53])
@pytest.mark.parametrize("prefix", ["FREQ=MONTHLY", "FREQ=YEARLY;BYMONTH=3"])
def test_month_ordinals_beyond_five_are_malformed(prefix, ordinal):
    with pytest.raises(ValueParseError):
        parse_rrule(f"{prefix};BYDAY={ordinal}TH")


@pytest.mark.parametrize("ordinal", [1, 6, 53, -1, -6, -53])
def test_yearly_ordinals_without_bymonth_allow_53(ordinal):
    rule = parse_rrule(f"FREQ=YEARLY;BYDAY={ordinal}SU")
    assert rule.byday == (WeekdayNum(6, ordinal),)


@pytest.mark.parametrize("ordinal", [0, 54, -54])
def test_yearly_ordinals_beyond_53_are_malformed(ordinal):
    with pytest.raises(ValueParseError):
        parse_rrule(f"FREQ=YEARLY;BYDAY={ordinal}SU")
