"""Property-based tests for daily-plan determinism.

Feature: flowly-mvp, Property 15: Daily plan is deterministic
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


# Feature: flowly-mvp, Property 15: Daily plan is deterministic
@settings(max_examples=200)
@given(
    st.lists(_task_strategy(), max_size=30, unique_by=lambda task: task.id),
    st.integers(min_value=0, max_value=5000),
)
def test_daily_plan_is_deterministic(tasks, available_minutes):
    # Generate the plan twice over identical inputs. The function is pure and
    # free of clock/DB/I/O, so the output must be identical both times
    # (Design 9; no ML/AI).
    first = generate_daily_plan(TARGET, tasks, available_minutes)
    second = generate_daily_plan(TARGET, tasks, available_minutes)

    # Top-level plan fields are identical.
    assert first.date == second.date
    assert first.available_minutes == second.available_minutes

    # The ordered list of planned tasks is identical in length and content,
    # position by position (same ids, estimates, priorities, deadlines, fits).
    assert len(first.planned_tasks) == len(second.planned_tasks)
    for a, b in zip(first.planned_tasks, second.planned_tasks):
        assert a == b
