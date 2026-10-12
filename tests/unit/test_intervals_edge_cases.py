"""Edge-case unit tests for the pure interval-union function.

Requirements 3.4; Design Testing Strategy (unit tests).
"""

from datetime import datetime

from app.planning.intervals import merge_intervals


def test_empty_set_returns_empty_list():
    assert merge_intervals([]) == []


def test_single_interval_returned_unchanged():
    assert merge_intervals([(10, 20)]) == [(10, 20)]


def test_back_to_back_adjacent_intervals_merge():
    # next_start == current_end -> adjacency merges into one interval.
    assert merge_intervals([(0, 10), (10, 20)]) == [(0, 20)]


def test_fully_nested_interval_absorbed():
    # The inner interval is entirely contained in the outer one.
    assert merge_intervals([(0, 100), (20, 40)]) == [(0, 100)]


def test_identical_intervals_collapse_to_one():
    assert merge_intervals([(5, 15), (5, 15), (5, 15)]) == [(5, 15)]


def test_disjoint_intervals_stay_separate():
    assert merge_intervals([(0, 5), (10, 15)]) == [(0, 5), (10, 15)]


def test_unsorted_input_is_sorted_before_merge():
    assert merge_intervals([(30, 40), (0, 10), (5, 20)]) == [(0, 20), (30, 40)]


def test_input_is_not_mutated():
    original = [(10, 20), (0, 5)]
    snapshot = list(original)
    merge_intervals(original)
    assert original == snapshot


def test_works_with_datetime_intervals():
    a = datetime(2025, 2, 10, 9, 0)
    b = datetime(2025, 2, 10, 10, 0)
    c = datetime(2025, 2, 10, 10, 30)
    d = datetime(2025, 2, 10, 11, 0)
    # (9-10) and (10-11) are adjacent at 10:00 -> merge; (10:30-11:00) nested.
    assert merge_intervals([(a, b), (b, d), (c, d)]) == [(a, d)]
