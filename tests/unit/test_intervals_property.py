"""Property-based tests for the pure interval-union function.

Feature: flowly-mvp, Property 9: Committed time is the union of intervals (no double-counting)
Validates: Requirements 3.4
"""

from hypothesis import given, settings, strategies as st

from app.planning.intervals import merge_intervals


def _interval_strategy():
    """Generate (start, end) integer intervals with start <= end."""
    return st.tuples(
        st.integers(min_value=0, max_value=1000),
        st.integers(min_value=0, max_value=1000),
    ).map(lambda pair: (min(pair), max(pair)))


def _total_length(intervals):
    return sum(end - start for start, end in intervals)


# Feature: flowly-mvp, Property 9: Committed time is the union of intervals (no double-counting)
@settings(max_examples=200)
@given(st.lists(_interval_strategy(), max_size=30))
def test_union_length_never_exceeds_sum_of_individual_lengths(intervals):
    merged = merge_intervals(intervals)
    assert _total_length(merged) <= _total_length(intervals)


# Feature: flowly-mvp, Property 9: Committed time is the union of intervals (no double-counting)
@settings(max_examples=200)
@given(st.lists(_interval_strategy(), min_size=1, max_size=30))
def test_merged_intervals_are_sorted_and_non_overlapping(intervals):
    merged = merge_intervals(intervals)
    # Sorted by start and strictly disjoint (not even adjacent: adjacency merges).
    for (prev_start, prev_end), (next_start, next_end) in zip(merged, merged[1:]):
        assert prev_start <= prev_end
        assert next_start > prev_end


# Feature: flowly-mvp, Property 9: Committed time is the union of intervals (no double-counting)
@settings(max_examples=200)
@given(st.lists(_interval_strategy(), max_size=30))
def test_merge_is_idempotent(intervals):
    once = merge_intervals(intervals)
    twice = merge_intervals(once)
    assert once == twice
