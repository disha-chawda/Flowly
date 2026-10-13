"""Property-based tests for daily-plan fitting within available time.

Feature: flowly-mvp, Property 16: Daily-plan fitting respects available time
Validates: Requirements 8
"""

from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

from hypothesis import given, settings, strategies as st

from app.domain.enums import Priority
from app.planning.daily_plan import generate_daily_plan

TARGET = date(2025, 2, 10)


def _task_strategy():
    """Generate a stand-in task with a deadline before/on/after the target or none.

    Deadlines are drawn as either a ``date`` or ``datetime`` offset in days from
    the target, spanning both sides of the target so some candidates qualify and
    some do not. ``None`` models a task with no deadline, which the selection
    rule excludes entirely (Design 9 step 1). ``estimated_time`` is sometimes
    ``None`` so the fitting rule's "missing estimate consumes 0" behavior is
    exercised, and ``created_at`` is offset so ties can be broken by creation
    time.
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


# Feature: flowly-mvp, Property 16: Daily-plan fitting respects available time

# Feature: flowly-mvp, Property 16: Daily-plan fitting respects available time
@settings(max_examples=200)
@given(
    st.lists(_task_strategy(), max_size=30, unique_by=lambda task: task.id),
    st.integers(min_value=0, max_value=5000),
)
def test_fitting_respects_available_time(tasks, available_minutes):
    result = generate_daily_plan(TARGET, tasks, available_minutes)

    # Recompute the running total independently, treating a missing estimate
    # as 0, and check every task's fits flag against it (Design 9 step 3).
    running = 0
    for planned in result.planned_tasks:
        running += planned.estimated_time or 0
        assert planned.fits == (running <= available_minutes)

    # Once a task does not fit, no later task fits: the flags must read
    # all True, then all False.
    flags = [planned.fits for planned in result.planned_tasks]
    assert flags == sorted(flags, reverse=True)
"""@settings(max_examples=200)
@given(
    st.lists(_task_strategy(), max_size=30, unique_by=lambda task: task.id),
    st.integers(min_value=0, max_value=5000),
)
def test_fitting_respects_available_time(tasks, available_minutes):
    result = generate_daily_plan(TARGET, tasks, available_minutes)

    # Sum the estimated time of every task marked as fitting, treating a
    # missing/None estimate as consuming 0 minutes (Design 9 step 3).
    running = 0
     for planned in result.planned_tasks:
        running += planned.estimated_time or 0
        assert planned.fits == (running <= available_minutes)
    # fitting_total = sum(
        #(planned.estimated_time or 0)
       # for planned in result.planned_tasks
        #if planned.fits

    # The cumulative estimate of tasks that fit must never exceed the
    # available minutes for the day.
    #assert fitting_total <= available_minutes
# Once a task does not fit, no later task fits: the flags must read
    # all True, then all False.
    flags = [planned.fits for planned in result.planned_tasks]
    assert flags == sorted(flags, reverse=True) """