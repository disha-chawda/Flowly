"""Property-based tests for daily-plan deterministic ordering.

Feature: flowly-mvp, Property 14: Daily-plan deterministic ordering
Validates: Requirements 8
"""

from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

from hypothesis import given, settings, strategies as st

from app.domain.enums import Priority
from app.planning.daily_plan import generate_daily_plan

TARGET = date(2025, 2, 10)

# Priority ordering for the plan: High first, then Medium, then Low (Design 9 step 2).
_PRIORITY_RANK = {
    Priority.HIGH: 0,
    Priority.MEDIUM: 1,
    Priority.LOW: 2,
}


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
    rule excludes entirely (Design 9 step 1). ``created_at`` is offset so ties on
    deadline and priority can be broken by creation time.
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


# Feature: flowly-mvp, Property 14: Daily-plan deterministic ordering
@settings(max_examples=200)
@given(
    st.lists(_task_strategy(), max_size=30, unique_by=lambda task: task.id),
    st.integers(min_value=0, max_value=5000),
)
def test_daily_plan_respects_deterministic_ordering(tasks, available_minutes):
    result = generate_daily_plan(TARGET, tasks, available_minutes)

    # PlannedTaskResult does not carry created_at, so map planned ids back to the
    # original task objects to verify the created_at tiebreak (Design 9 step 2).
    by_id = {task.id: task for task in tasks}

    planned = result.planned_tasks
    for earlier, later in zip(planned, planned[1:]):
        a = by_id[earlier.id]
        b = by_id[later.id]

        a_deadline = _deadline_date(a.deadline)
        b_deadline = _deadline_date(b.deadline)

        # 1. Deadline ascending (earlier first).
        assert a_deadline <= b_deadline

        if a_deadline == b_deadline:
            a_rank = _PRIORITY_RANK[a.priority]
            b_rank = _PRIORITY_RANK[b.priority]
            # 2. Priority High > Medium > Low on a deadline tie.
            assert a_rank <= b_rank

            if a_rank == b_rank:
                # 3. created_at ascending on a deadline + priority tie.
                assert a.created_at <= b.created_at
