"""Property-based tests for the estimated-minutes sum rule.

Feature: flowly-mvp, Property 11: Estimated minutes sum treats missing estimates as zero
Validates: Requirements 2.4, 7
"""

from datetime import date
from types import SimpleNamespace

from hypothesis import given, settings, strategies as st

from app.planning.workload import compute_workload

TARGET = date(2025, 2, 10)


def _task_strategy():
    """Generate a stand-in task that may or may not carry an ``estimated_time``.

    ``None`` models a task with a missing estimate; an integer models a task
    with an explicit estimate in minutes. Mixing both exercises the rule that a
    missing estimate contributes 0 to the sum (Requirements 2.4).
    """
    return st.builds(
        lambda estimate: SimpleNamespace(estimated_time=estimate),
        st.one_of(st.none(), st.integers(min_value=0, max_value=1440)),
    )


# Feature: flowly-mvp, Property 11: Estimated minutes sum treats missing estimates as zero
@settings(max_examples=200)
@given(st.lists(_task_strategy(), max_size=30))
def test_estimated_minutes_sum_treats_missing_as_zero(tasks):
    result = compute_workload(TARGET, tasks, [])

    expected = sum(
        task.estimated_time for task in tasks if task.estimated_time is not None
    )

    assert result.estimated_minutes == expected
