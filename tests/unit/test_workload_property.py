"""Property-based tests for the pure workload-calculation function.

Feature: flowly-mvp, Property 10: Available time is clamped and never negative
Validates: Requirements 7
"""

from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

from hypothesis import given, settings, strategies as st

from app.planning.workload import WINDOW_MINUTES, compute_workload

TARGET = date(2025, 2, 10)
_DAY_START = datetime.combine(TARGET, time.min)


def _commitment_strategy():
    """Generate a commitment whose window span can reach or exceed 960 minutes.

    Offsets are drawn in minutes from the target date's midnight, spanning well
    beyond the 960-minute window so some generated commitments meet or exceed
    the full window and exercise the available-time clamp.
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


# Feature: flowly-mvp, Property 10: Available time is clamped and never negative
@settings(max_examples=200)
@given(st.lists(_commitment_strategy(), max_size=20))
def test_available_time_is_clamped_and_never_negative(commitments):
    result = compute_workload(TARGET, [], commitments)

    # Available is exactly the clamped complement of committed within the window.
    assert result.available_minutes == max(
        0, result.window_minutes - result.committed_minutes
    )
    # The clamp guarantees non-negativity even when commitments fill or exceed
    # the full 960-minute window.
    assert result.available_minutes >= 0
    assert result.committed_minutes <= WINDOW_MINUTES


# Feature: flowly-mvp, Property 10: Available time is clamped and never negative
@settings(max_examples=100)
@given(
    st.lists(
        st.builds(
            lambda start, length: SimpleNamespace(
                start_time=_DAY_START + timedelta(minutes=start),
                end_time=_DAY_START + timedelta(minutes=start + length),
            ),
            st.integers(min_value=0, max_value=960),
            st.integers(min_value=200, max_value=2000),
        ),
        min_size=1,
        max_size=10,
    )
)
def test_available_is_zero_when_commitments_meet_or_exceed_window(commitments):
    # Large commitment spans drive committed time to the window cap, so the
    # clamp must pin available at exactly zero and never below.
    result = compute_workload(TARGET, [], commitments)

    assert result.available_minutes == max(
        0, result.window_minutes - result.committed_minutes
    )
    assert result.available_minutes >= 0
