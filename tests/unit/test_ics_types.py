"""Unit tests for the shared ``app.ics`` types (Design 4.1).

Validates: Requirements 10.4, 12.3
"""

import dataclasses
from datetime import datetime

import pytest

import app.ics as ics
from app.ics import (
    ImportLimits,
    ImportRecord,
    InvalidCalendarError,
    ParseResult,
    SkippedItem,
    SkipReason,
)


def test_skip_reason_codes_are_the_fixed_set():
    assert {reason.value for reason in SkipReason} == {
        "unchanged",
        "duplicate",
        "missing_uid",
        "missing_start",
        "invalid_interval",
        "all_day",
        "cancelled",
        "unknown_timezone",
        "dst_overlap",
        "unsupported_recurrence",
        "outside_window",
        "past_event",
        "malformed_event",
    }
    assert SkipReason("past_event") is SkipReason.PAST_EVENT
    assert SkipReason.PAST_EVENT == "past_event"


def test_import_limits_defaults():
    limits = ImportLimits()
    assert (limits.max_records, limits.max_examined_dates, limits.window_days) == (
        2_000,
        200_000,
        180,
    )


def test_dataclasses_are_frozen_and_comparable():
    start, end = datetime(2026, 11, 2, 9), datetime(2026, 11, 2, 10)
    record = ImportRecord("S|abc", "abc", "CS 101", start, end)
    assert record == ImportRecord("S|abc", "abc", "CS 101", start, end)
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.title = "changed"

    result = ParseResult(records=(record,), skipped=())
    assert result == ParseResult(records=(record,), skipped=())


def test_skipped_item_count_defaults_to_one():
    item = SkippedItem("abc", "Reading week", None, SkipReason.ALL_DAY, "All-day events are not imported.")
    assert item.count == 1

    aggregate = SkippedItem(None, None, None, SkipReason.PAST_EVENT, "312 events ended before ...", count=312)
    assert aggregate.count == 312


def test_invalid_calendar_error_carries_issue():
    error = InvalidCalendarError("The file is empty.")
    assert isinstance(error, ValueError)
    assert error.issue == "The file is empty."
    assert str(error) == "The file is empty."


def test_package_reexports_public_types():
    assert set(ics.__all__) >= {
        "ImportLimits",
        "ImportRecord",
        "InvalidCalendarError",
        "ParseResult",
        "SkippedItem",
        "SkipReason",
    }
