"""Pure interval-union helpers for the FLOWLY planning core.

No database, clock, or I/O. Functions depend only on their inputs so they are
deterministic and testable in isolation (Design 1, Testing Strategy).
"""


def merge_intervals(intervals):
    """Merge a collection of (start, end) intervals into their union.

    Sort the intervals by start, then walk left to right: when the next
    interval starts at or before the current interval's end
    (``next_start <= current_end``), extend the current interval; otherwise
    close the current interval and open a new one.

    Args:
        intervals: An iterable of ``(start, end)`` pairs. ``start`` and ``end``
            must be mutually comparable (e.g. ``datetime`` or numbers). Each
            interval is expected to satisfy ``start <= end``.

    Returns:
        A new list of merged, non-overlapping ``(start, end)`` tuples sorted by
        start. The input is not mutated.
    """
    ordered = sorted(((start, end) for start, end in intervals), key=lambda pair: pair[0])
    if not ordered:
        return []

    merged = []
    current_start, current_end = ordered[0]
    for next_start, next_end in ordered[1:]:
        if next_start <= current_end:
            # Overlapping or adjacent: extend the current interval.
            if next_end > current_end:
                current_end = next_end
        else:
            # Disjoint: close the current interval and start a new one.
            merged.append((current_start, current_end))
            current_start, current_end = next_start, next_end
    merged.append((current_start, current_end))
    return merged

""" The whole idea in one sentence: sort the intervals, then sweep left to right, growing the current block while things overlap and starting a new block whenever there’s a gap. """