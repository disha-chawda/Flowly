"""Property-based tests for the overload-flag rule.

Feature: flowly-mvp, Property 12: Overload flag matches strict comparison
Validates: Requirements 7
"""

from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

from hypothesis import given, settings, strategies as st

from app.planning.workload import compute_workload

TARGET = date(2025, 2, 10)
_DAY_START = datetime.combine(TARGET, time.min)


def _task_strategy():
    """Generate a stand-in task that may or may not carry an ``estimated_time``.

    ``None`` models a missing estimate (contributes 0 to the sum); an integer
    models an explicit estimate in minutes. Estimates range across the full
    window and beyond so the estimated total straddles the available-time
    boundary (below, equal to, and above) across generated cases.
    """
    return st.builds(
        lambda estimate: SimpleNamespace(estimated_time=estimate),
        st.one_of(st.none(), st.integers(min_value=0, max_value=1200)),
    )


def _commitment_strategy():
    """Generate a commitment clipped against the 960-minute window.

    Offsets span beyond the window so available time varies widely between
    cases, which in turn moves the strict-comparison boundary against the
    generated estimated totals.
    """
    return st.tuples(
        st.integers(min_value=-120, max_value=1200),
        st.integers(min_value=-120, max_value=1200),
    ).map(lambda pair: (min(pair), max(pair))).map(
        lambda pair: SimpleNamespace(
            start_time=_DAY_START + timedelta(minutes=pair[0]),
            end_time=_DAY_START + timedelta(minutes=pair[1]),
        )
    )


# Feature: flowly-mvp, Property 12: Overload flag matches strict comparison
@settings(max_examples=200)
@given(
    st.lists(_task_strategy(), max_size=30),
    st.lists(_commitment_strategy(), max_size=20),
)
def test_overload_flag_matches_strict_comparison(tasks, commitments):
    result = compute_workload(TARGET, tasks, commitments)

    # ``overloaded`` is true iff estimated STRICTLY exceeds available: the exact
    # strict comparison, holding across every generated boundary case.
    assert result.overloaded == (
        result.estimated_minutes > result.available_minutes
    )

    # Equality is the boundary: estimated exactly equal to available is NOT
    # overloaded under the strict rule.
    if result.estimated_minutes == result.available_minutes:
        assert result.overloaded is False
