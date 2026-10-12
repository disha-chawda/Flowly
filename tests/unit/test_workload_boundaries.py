"""Unit tests for workload boundary conditions.

Exercise the edges of ``compute_workload`` where the simple arithmetic rules
are most likely to be off by one: a commitment that consumes the entire
window, an estimate that exactly matches available time, and empty inputs.

Requirements 7 (Workload Summary); Design 8 / Testing Strategy (unit tests).
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


def _task(estimated_time):
    """Build a stand-in task carrying an ``estimated_time`` in minutes."""
    return SimpleNamespace(estimated_time=estimated_time)


def test_commitment_fills_full_window_leaves_zero_available():
    # 00:00-16:00 is exactly the 960-minute window: committed hits the cap and
    # available collapses to 0.
    commitments = [_commitment(0, 0, 16, 0)]

    result = compute_workload(TARGET, [], commitments)

    assert result.committed_minutes == WINDOW_MINUTES
    assert result.available_minutes == 0
    # No tasks, so estimated is 0 and difference equals available (0).
    assert result.estimated_minutes == 0
    assert result.difference_minutes == 0
    assert result.overloaded is False


def test_estimated_equal_to_available_is_not_overloaded():
    # Available is the full window (no commitments). An estimate that exactly
    # equals available is NOT overloaded because overload is strict (> ).
    tasks = [_task(WINDOW_MINUTES)]

    result = compute_workload(TARGET, tasks, [])

    assert result.available_minutes == WINDOW_MINUTES
    assert result.estimated_minutes == WINDOW_MINUTES
    assert result.difference_minutes == 0
    assert result.overloaded is False


def test_estimated_one_minute_over_available_is_overloaded():
    # Boundary partner to the equality case: one minute past available flips
    # overloaded to True and drives difference negative.
    tasks = [_task(WINDOW_MINUTES + 1)]

    result = compute_workload(TARGET, tasks, [])

    assert result.available_minutes == WINDOW_MINUTES
    assert result.estimated_minutes == WINDOW_MINUTES + 1
    assert result.difference_minutes == -1
    assert result.overloaded is True


def test_empty_inputs_yield_full_available_window():
    # No tasks and no commitments: nothing committed, nothing estimated, the
    # whole window is available and the day is not overloaded.
    result = compute_workload(TARGET, [], [])

    assert result.window_minutes == WINDOW_MINUTES
    assert result.committed_minutes == 0
    assert result.available_minutes == WINDOW_MINUTES
    assert result.estimated_minutes == 0
    assert result.difference_minutes == WINDOW_MINUTES
    assert result.overloaded is False
