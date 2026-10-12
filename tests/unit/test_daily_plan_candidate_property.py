"""Property-based tests for daily-plan candidate selection.

Feature: flowly-mvp, Property 13: Daily-plan candidate selection
Validates: Requirements 8
"""

from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

from hypothesis import given, settings, strategies as st

from app.domain.enums import Priority
from app.planning.daily_plan import generate_daily_plan

TARGET = date(2025, 2, 10)


def _deadline_date(deadline):
    """Return the ``date`` component of a deadline ``date`` or ``datetime``."""
    if isinstance(deadline, datetime):
        return deadline.date()
    return deadline


def _task_strategy():
    """Generate a stand-in task with a deadline before/on/after the target or none.

    Deadlines are drawn as either a ``date`` or ``datetime`` offset in days from
    the target, spanning both sides of the target so some candidates qualify and
    some do not. ``None`` models a task with no deadline, which the selection
    rule excludes entirely (Design 9 step 1).
    """
    deadlines = st.one_of(
        st.none(),
        st.builds(
            lambda offset: TARGET + timedelta(days=offset),
            st.integers(min_value=-10, max_value=10),
        ),
        st.builds(
            lambda offset, t: datetime.combine(
                TARGET + timedelta(days=offset), t
            ),
            st.integers(min_value=-10, max_value=10),
            st.times(),
        ),
    )
    return st.builds(
        lambda tid, estimate, priority, deadline, created_offset: SimpleNamespace(
            id=tid,
            title=f"task-{tid}",
            estimated_time=estimate,
            priority=priority,
            created_at=datetime.combine(TARGET, time.min)
            + timedelta(minutes=created_offset),
            deadline=deadline,
        ),
        st.integers(min_value=1, max_value=10_000),
        st.one_of(st.none(), st.integers(min_value=0, max_value=1440)),
        st.sampled_from(list(Priority)),
        deadlines,
        st.integers(min_value=0, max_value=100_000),
    )


# Feature: flowly-mvp, Property 13: Daily-plan candidate selection
@settings(max_examples=200)
@given(
    st.lists(_task_strategy(), max_size=30, unique_by=lambda task: task.id),
    st.integers(min_value=0, max_value=5000),
)
def test_candidate_selection_matches_deadline_rule(tasks, available_minutes):
    result = generate_daily_plan(TARGET, tasks, available_minutes)

    # Independently compute the ids that should be candidates: tasks with a
    # defined deadline on or before the target date (Design 9 step 1).
    expected_ids = {
        task.id
        for task in tasks
        if task.deadline is not None and _deadline_date(task.deadline) <= TARGET
    }
    planned_ids = {planned.id for planned in result.planned_tasks}

    # The plan includes exactly the qualifying candidates.
    assert planned_ids == expected_ids

    # No task with a missing deadline ever appears in the plan.
    no_deadline_ids = {task.id for task in tasks if task.deadline is None}
    assert planned_ids.isdisjoint(no_deadline_ids)
