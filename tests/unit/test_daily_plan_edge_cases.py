"""Unit tests for daily-plan edge cases.

Covers specific examples the planning-core property tests generalize over:
tie-breaking by ``created_at``, the available-time cutoff partway through the
ordered list, and an all-no-deadline input (Design 9; Testing Strategy).

Validates: Requirements 8
"""

from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

from app.domain.enums import Priority
from app.planning.daily_plan import generate_daily_plan

TARGET = date(2025, 2, 10)


def _task(
    tid,
    *,
    deadline=TARGET,
    priority=Priority.MEDIUM,
    estimated_time=None,
    created_offset=0,
):
    """Build a stand-in task mirroring the fields the planner reads.

    ``created_offset`` is minutes added to midnight of the target so creation
    times can be ordered deterministically.
    """
    return SimpleNamespace(
        id=tid,
        title=f"task-{tid}",
        estimated_time=estimated_time,
        priority=priority,
        created_at=datetime.combine(TARGET, time.min)
        + timedelta(minutes=created_offset),
        deadline=deadline,
    )


def test_equal_deadline_and_priority_orders_by_created_at_ascending():
    """With deadline and priority tied, earlier ``created_at`` comes first.

    Tasks are supplied out of creation order to prove the planner sorts rather
    than preserving input order (Design 9 step 2, third tiebreak).
    """
    first = _task(1, created_offset=0)
    middle = _task(2, created_offset=30)
    last = _task(3, created_offset=60)

    # Supplied shuffled so a passing result cannot be input-order coincidence.
    result = generate_daily_plan(TARGET, [last, first, middle], available_minutes=1000)

    assert [planned.id for planned in result.planned_tasks] == [1, 2, 3]


def test_available_time_runs_out_partway_without_reordering():
    """Tasks before the cutoff fit; those after do not, and order is unchanged.

    Four equal-deadline, equal-priority tasks of 30 minutes each are ordered by
    ``created_at``. With 60 available minutes, the first two fit (30, 60) and the
    last two do not (90, 120). The cutoff only flips ``fits`` — it never reorders
    (Design 9 step 3).
    """
    tasks = [
        _task(1, estimated_time=30, created_offset=0),
        _task(2, estimated_time=30, created_offset=10),
        _task(3, estimated_time=30, created_offset=20),
        _task(4, estimated_time=30, created_offset=30),
    ]

    result = generate_daily_plan(TARGET, tasks, available_minutes=60)

    assert [planned.id for planned in result.planned_tasks] == [1, 2, 3, 4]
    assert [planned.fits for planned in result.planned_tasks] == [
        True,
        True,
        False,
        False,
    ]


def test_all_no_deadline_input_produces_empty_plan():
    """No-deadline tasks are excluded entirely, yielding an empty plan.

    The plan metadata (date, available_minutes) still reflects the request
    (Design 9 step 1).
    """
    tasks = [
        _task(1, deadline=None),
        _task(2, deadline=None, priority=Priority.HIGH),
        _task(3, deadline=None, estimated_time=120),
    ]

    result = generate_daily_plan(TARGET, tasks, available_minutes=480)

    assert result.planned_tasks == []
    assert result.date == TARGET
    assert result.available_minutes == 480


def test_same_day_tasks_ordered_by_priority_not_time_of_day():
    """Same deadline date: priority decides, not the time of day.

    A Low task due at 09:00 and a High task due at 17:00 on the same date must
    come out High first. Sorting by the raw datetime would put Low first.
    """
    low_morning = _task(
        1,
        deadline=datetime.combine(TARGET, time(9, 0)),
        priority=Priority.LOW,
    )
    high_evening = _task(
        2,
        deadline=datetime.combine(TARGET, time(17, 0)),
        priority=Priority.HIGH,
    )

    result = generate_daily_plan(TARGET, [low_morning, high_evening], available_minutes=1000)

    assert [planned.id for planned in result.planned_tasks] == [2, 1]


def test_overdue_task_is_included_and_ordered_first():
    """A deadline before the target date is still a candidate, and sorts first."""
    overdue = _task(1, deadline=date(2025, 2, 1), priority=Priority.LOW)
    due_today = _task(2, deadline=TARGET, priority=Priority.HIGH)

    result = generate_daily_plan(TARGET, [due_today, overdue], available_minutes=1000)

    assert [planned.id for planned in result.planned_tasks] == [1, 2]