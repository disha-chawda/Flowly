"""Pure workload-calculation for the FLOWLY planning core.

No database, clock, or I/O. ``compute_workload`` depends only on its inputs so
it is deterministic and testable in isolation (Design 1, 8; Testing Strategy).

The daily planning window is a fixed 16 hours = 960 minutes, a stated temporary
MVP assumption (Design 8; Requirements 7).
"""

from dataclasses import dataclass
from datetime import datetime, time

from app.planning.intervals import merge_intervals

# Fixed 16-hour MVP planning window, expressed in minutes (Design 8, Requirements 7).
WINDOW_MINUTES = 960


@dataclass(frozen=True)
class WorkloadResult:
    """Plain result of a workload calculation.

    Fields mirror the ``WorkloadSummary`` shape in Design 6 so the service layer
    can map this straight onto the Pydantic response without the pure function
    depending on Pydantic.
    """

    date: object
    window_minutes: int
    committed_minutes: int
    available_minutes: int
    estimated_minutes: int
    difference_minutes: int
    overloaded: bool


def _target_date(date):
    """Return the ``date`` component of a ``date`` or ``datetime`` input."""
    if isinstance(date, datetime):
        return date.date()
    return date


def _clip_commitment_to_window(start_time, end_time, target):
    """Clip a commitment to the target date's 960-minute window.

    Convert the clipped interval to minutes measured from the start of the
    target date (midnight), bounded to ``[0, WINDOW_MINUTES]``. Returns ``None``
    when the commitment does not touch the window at all.

    Args:
        start_time: Commitment start as a ``datetime``.
        end_time: Commitment end as a ``datetime``.
        target: The target ``date``.

    Returns:
        A ``(start_minute, end_minute)`` pair within the window, or ``None`` if
        the commitment falls entirely outside the window.
    """
    day_start = datetime.combine(target, time.min)

    start_minute = (start_time - day_start).total_seconds() / 60.0
    end_minute = (end_time - day_start).total_seconds() / 60.0

    # Clip to the window bounds [0, WINDOW_MINUTES].
    start_minute = max(0.0, min(start_minute, WINDOW_MINUTES))
    end_minute = max(0.0, min(end_minute, WINDOW_MINUTES))

    if end_minute <= start_minute:
        # Zero-length after clipping, or entirely outside the window.
        return None
    return (start_minute, end_minute)


def compute_workload(date, tasks, commitments):
    """Compute the workload summary for ``date`` from tasks and commitments.

    Pure and deterministic: no clock, DB, or I/O. All inputs are already-loaded
    plain objects (Design 8).

    Steps (Design 8):
        1. Window is a fixed 960 minutes.
        2. Committed time is the length of the *union* of the commitment
           intervals clipped to the window, so overlapping time is counted once
           (reuses ``merge_intervals``).
        3. ``available = max(0, 960 - committed)`` — clamped, never negative.
        4. Estimated time sums each task's ``estimated_time``; a missing/None
           estimate contributes 0.
        5. ``difference = available - estimated`` — reported as-is, may be
           negative (only *available* is clamped).
        6. ``overloaded = estimated > available`` — strict comparison.

    Args:
        date: The target ``date`` (or ``datetime``; only the date part is used).
        tasks: Iterable of incomplete tasks due that date. Each may expose an
            optional ``estimated_time`` (minutes); missing/None counts as 0.
        commitments: Iterable of commitments, each with ``start_time`` and
            ``end_time`` datetimes.

    Returns:
        A ``WorkloadResult`` carrying the fields of Design 6's
        ``WorkloadSummary``.
    """
    target = _target_date(date)

    # Committed: union of clipped commitment intervals, summed once (Design 8 step 2).
    clipped = []
    for commitment in commitments:
        interval = _clip_commitment_to_window(
            commitment.start_time, commitment.end_time, target
        )
        if interval is not None:
            clipped.append(interval)

    committed = sum(end - start for start, end in merge_intervals(clipped))
    committed_minutes = int(round(committed))

    # Available: clamped at >= 0 (Design 8 step 3).
    available_minutes = max(0, WINDOW_MINUTES - committed_minutes)

    # Estimated: sum of estimated_time, missing/None => 0 (Design 8 step 4).
    estimated_minutes = 0
    for task in tasks:
        estimate = getattr(task, "estimated_time", None)
        if estimate is not None:
            estimated_minutes += estimate

    # Difference: not clamped, may be negative (Design 8 step 5).
    difference_minutes = available_minutes - estimated_minutes

    # Overload: strict comparison (Design 8 step 6).
    overloaded = estimated_minutes > available_minutes

    return WorkloadResult(
        date=target,
        window_minutes=WINDOW_MINUTES,
        committed_minutes=committed_minutes,
        available_minutes=available_minutes,
        estimated_minutes=estimated_minutes,
        difference_minutes=difference_minutes,
        overloaded=overloaded,
    )
