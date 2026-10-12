"""Unit tests for committed time within the fixed planning window.

Verify that ``compute_workload`` never counts more than the 960-minute
planning window as committed time, regardless of how commitments overlap,
extend past the window, or fill it entirely.

Requirements 7; Design 8.
"""

from datetime import date, datetime
from types import SimpleNamespace

from app.planning.workload import WINDOW_MINUTES, compute_workload

TARGET = date(2025, 2, 10)


def _commitment(start_hour, start_minute, end_hour, end_minute):
    """Build a stand-in commitment with ``start_time`` / ``end_time`` datetimes."""
    return SimpleNamespace(
        start_time=datetime(TARGET.year, TARGET.month, TARGET.day, start_hour, start_minute),
        end_time=datetime(TARGET.year, TARGET.month, TARGET.day, end_hour, end_minute),
    )


def test_overlapping_commitments_counted_once():
    # 08:00-10:00 (120 min) and 09:00-11:00 (120 min) overlap one hour.
    # Union is 08:00-11:00 = 180 minutes, not the 240-minute naive sum.
    commitments = [
        _commitment(8, 0, 10, 0),
        _commitment(9, 0, 11, 0),
    ]

    result = compute_workload(TARGET, [], commitments)

    assert result.committed_minutes == 180
    assert result.committed_minutes <= WINDOW_MINUTES


def test_commitment_extending_beyond_window_is_clipped():
    # 14:00-20:00: only the portion inside the window (14:00-16:00 = 120 min) counts.
    commitments = [_commitment(14, 0, 20, 0)]

    result = compute_workload(TARGET, [], commitments)

    assert result.committed_minutes == 120
    assert result.committed_minutes <= WINDOW_MINUTES


def test_commitment_filling_full_window_caps_at_window():
    # 00:00-16:00 exactly fills the 960-minute window.
    commitments = [_commitment(0, 0, 16, 0)]

    result = compute_workload(TARGET, [], commitments)

    assert result.committed_minutes == WINDOW_MINUTES
    assert result.available_minutes == 0
    assert result.committed_minutes <= WINDOW_MINUTES


def test_commitment_exceeding_full_window_caps_at_window():
    # 00:00-23:59 exceeds the window; committed is still clamped to 960 and
    # available drops to zero.
    commitments = [_commitment(0, 0, 23, 59)]

    result = compute_workload(TARGET, [], commitments)

    assert result.committed_minutes == WINDOW_MINUTES
    assert result.available_minutes == 0
    assert result.committed_minutes <= WINDOW_MINUTES
