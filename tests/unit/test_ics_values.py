"""Unit tests for scalar ICS value parsing (Design 4.3).

Validates: Requirements 3.12, 7.1, 8.1, 8.7
"""

from datetime import date, datetime, timedelta

import pytest

from app.ics.values import (
    DateTimeValue,
    DurationValue,
    ValueParseError,
    parse_date,
    parse_date_or_date_time,
    parse_date_or_date_time_list,
    parse_date_time,
    parse_duration,
    unescape_text,
)


# --- DATE-TIME -------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("20261102T090000", DateTimeValue(datetime(2026, 11, 2, 9, 0, 0), utc=False)),
        ("20261102T140000Z", DateTimeValue(datetime(2026, 11, 2, 14, 0, 0), utc=True)),
        ("20240229T235959", DateTimeValue(datetime(2024, 2, 29, 23, 59, 59), utc=False)),
        ("00010101T000000", DateTimeValue(datetime(1, 1, 1), utc=False)),
    ],
)
def test_parse_date_time_valid(raw, expected):
    assert parse_date_time(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "20260230T090000",  # February 30
        "20250229T090000",  # not a leap year
        "20261102T090060",  # leap second
        "20261102T240000",
        "20261302T090000",
        "00000101T000000",  # year 0
        "20261102T0900",  # too short
        "20261102 090000",
        "20261102T090000z",
        "20261102T090000+0100",
        "2026-11-02T09:00:00",
        "20261102",  # a DATE, not a DATE-TIME
        "２０２６1102T090000",  # non-ASCII digits
        "",
    ],
)
def test_parse_date_time_invalid(raw):
    with pytest.raises(ValueParseError):
        parse_date_time(raw)


def test_value_parse_error_is_a_value_error():
    assert issubclass(ValueParseError, ValueError)


# --- DATE ------------------------------------------------------------------


def test_parse_date_valid():
    assert parse_date("20261225") == date(2026, 12, 25)


@pytest.mark.parametrize("raw", ["20260230", "2026122", "20261225T000000", "2026-12-25", ""])
def test_parse_date_invalid(raw):
    with pytest.raises(ValueParseError):
        parse_date(raw)


def test_bare_date_form_is_a_date():
    result = parse_date_or_date_time("20261225")
    assert result == date(2026, 12, 25)
    assert not isinstance(result, datetime)


def test_value_date_parameter_gives_a_date():
    assert parse_date_or_date_time("20261225", "DATE") == date(2026, 12, 25)
    assert parse_date_or_date_time("20261225", "date") == date(2026, 12, 25)


def test_date_time_form_without_parameter():
    assert parse_date_or_date_time("20261225T090000Z") == DateTimeValue(
        datetime(2026, 12, 25, 9), utc=True
    )


@pytest.mark.parametrize(
    ("raw", "value_type"),
    [
        ("20261225T090000", "DATE"),  # VALUE=DATE requires a DATE
        ("20261225", "DATE-TIME"),  # VALUE=DATE-TIME requires a DATE-TIME
        ("20261225T090000/PT1H", "PERIOD"),
        ("20261225", "TEXT"),
        ("20261232", None),
    ],
)
def test_parse_date_or_date_time_invalid(raw, value_type):
    with pytest.raises(ValueParseError):
        parse_date_or_date_time(raw, value_type)


def test_date_list():
    assert parse_date_or_date_time_list("20261102T090000,20261109T090000") == (
        DateTimeValue(datetime(2026, 11, 2, 9), utc=False),
        DateTimeValue(datetime(2026, 11, 9, 9), utc=False),
    )
    assert parse_date_or_date_time_list("20261225", "DATE") == (date(2026, 12, 25),)


@pytest.mark.parametrize("raw", ["", "20261102T090000,", "20261102T090000,,20261109T090000"])
def test_date_list_rejects_empty_items(raw):
    with pytest.raises(ValueParseError):
        parse_date_or_date_time_list(raw)


# --- DURATION --------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("PT0S", DurationValue(0, timedelta(0))),
        ("-PT1H", DurationValue(0, timedelta(hours=-1))),
        ("+PT1H", DurationValue(0, timedelta(hours=1))),
        ("P1W", DurationValue(7, timedelta(0))),
        ("-P2W", DurationValue(-14, timedelta(0))),
        ("P1D", DurationValue(1, timedelta(0))),
        ("P1DT2H", DurationValue(1, timedelta(hours=2))),
        ("P15DT5H0M20S", DurationValue(15, timedelta(hours=5, seconds=20))),
        ("PT90M", DurationValue(0, timedelta(minutes=90))),
        ("PT1H30M", DurationValue(0, timedelta(hours=1, minutes=30))),
        ("PT45S", DurationValue(0, timedelta(seconds=45))),
        ("-P1DT1H", DurationValue(-1, timedelta(hours=-1))),
    ],
)
def test_parse_duration_valid(raw, expected):
    assert parse_duration(raw) == expected


def test_duration_keeps_nominal_and_exact_parts_separate():
    # One day stays nominal and 24 hours stays exact, so DST days differ (Design 4.4).
    assert parse_duration("P1D") != parse_duration("PT24H")
    assert parse_duration("PT24H") == DurationValue(0, timedelta(hours=24))


@pytest.mark.parametrize(
    "raw",
    [
        "P",
        "PT",
        "-P",
        "P1DT",
        "1H",
        "PT1H2D",  # D after T
        "P1W2D",  # weeks cannot combine with days
        "P1.5D",
        "PT-1H",
        "P1Y",
        "P1M",  # months are not allowed outside T
        "pt1h",
        "",
        "P" + "9" * 20 + "D",  # too large for a timedelta
        "PT" + "9" * 5000 + "S",  # beyond int conversion limit
    ],
)
def test_parse_duration_invalid(raw):
    with pytest.raises(ValueParseError):
        parse_duration(raw)


# --- TEXT ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("CS 101", "CS 101"),
        (r"a\\b", "a\\b"),
        (r"a\;b", "a;b"),
        (r"a\,b", "a,b"),
        (r"line1\nline2", "line1\nline2"),
        (r"line1\Nline2", "line1\nline2"),
        (r"Lab\, room 2\; bring laptop\\charger\n", "Lab, room 2; bring laptop\\charger\n"),
        (r"\\n", "\\n"),  # escaped backslash followed by a literal n
        (r"\\\,", "\\,"),
    ],
)
def test_unescape_text(raw, expected):
    assert unescape_text(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (r"Time\: 9am", r"Time\: 9am"),  # unknown escape kept as written
        ("trailing\\", "trailing\\"),
        ("", ""),
    ],
)
def test_unescape_text_is_lenient(raw, expected):
    assert unescape_text(raw) == expected
