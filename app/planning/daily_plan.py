"""Pure daily-planning algorithm for the FLOWLY planning core.

No database, clock, or I/O. ``generate_daily_plan`` depends only on its inputs
so it is deterministic and testable in isolation (Design 1, 9; Testing Strategy).
No ML/AI: the same inputs always yield the same ordered plan (Design 9).

The result mirrors the ``DailyPlan`` / ``PlannedTask`` shapes in Design 6 so the
service layer can map it straight onto the Pydantic response without the pure
function depending on Pydantic.
"""

from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import Priority

# Priority ordering for the plan: High first, then Medium, then Low (Design 9 step 2).
_PRIORITY_RANK = {
    Priority.HIGH: 0,
    Priority.MEDIUM: 1,
    Priority.LOW: 2,
}


@dataclass(frozen=True)
class PlannedTaskResult:
    """A single task in the plan, carrying its deterministic fit annotation.

    Fields mirror the ``PlannedTask`` shape in Design 6.
    """

    id: object
    title: str
    estimated_time: int | None
    priority: object
    deadline: object
    fits: bool


@dataclass(frozen=True)
class DailyPlanResult:
    """Plain result of a daily-plan computation.

    Fields mirror the ``DailyPlan`` shape in Design 6.
    """

    date: object
    available_minutes: int
    planned_tasks: list


def _target_date(date):
    """Return the ``date`` component of a ``date`` or ``datetime`` input."""
    if isinstance(date, datetime):
        return date.date()
    return date


def _deadline_date(deadline):
    """Return the ``date`` component of a deadline ``date`` or ``datetime``."""
    if isinstance(deadline, datetime):
        return deadline.date()
    return deadline


def _ordering_key(task):
    """Build the strict, total ordering key for a candidate task (Design 9 step 2).

    1. Deadline ascending (earlier first).
    2. Priority High > Medium > Low.
    3. ``created_at`` ascending (earlier creation first).
    """
    return (
        _deadline_date(task.deadline),
        _PRIORITY_RANK.get(task.priority, len(_PRIORITY_RANK)),
        task.created_at,
    )


def generate_daily_plan(date, tasks, available_minutes):
    """Generate the deterministic daily plan for ``date``.

    Pure and deterministic: no clock, DB, or I/O. All inputs are already-loaded
    plain objects (Design 9).

    Steps (Design 9):
        1. Candidate selection: include an incomplete task only when it has a
           defined deadline on or before the target date. Tasks with no deadline
           are excluded entirely.
        2. Deterministic ordering: deadline ascending, then priority
           High > Medium > Low, then ``created_at`` ascending.
        3. Fitting: walk the ordered list accumulating ``estimated_time`` (a
           missing/None estimate consumes 0) and mark each task's ``fits`` flag
           by whether the running total stays within ``available_minutes``. The
           ordering itself never changes based on fit.

    Args:
        date: The target ``date`` (or ``datetime``; only the date part is used).
        tasks: Iterable of incomplete tasks. Each exposes ``deadline`` (optional
            ``datetime``/``date``), ``estimated_time`` (optional minutes),
            ``priority``, ``created_at``, ``id``, and ``title``. Candidate
            selection assumes the tasks passed in are incomplete.
        available_minutes: The available minutes for the day (from the workload
            calculation, Design 8).

    Returns:
        A ``DailyPlanResult`` carrying the fields of Design 6's ``DailyPlan``.
    """
    target = _target_date(date)

    # Step 1 — Candidate selection: incomplete tasks with a deadline on or
    # before the target date; no-deadline tasks are excluded (Design 9 step 1).
    candidates = [
        task
        for task in tasks
        if task.deadline is not None and _deadline_date(task.deadline) <= target
    ]

    # Step 2 — Deterministic ordering (Design 9 step 2).
    ordered = sorted(candidates, key=_ordering_key)

    # Step 3 — Fit annotation layered on top of the deterministic order
    # (Design 9 step 3). Fit never reorders the list.
    planned_tasks = []
    consumed = 0
    for task in ordered:
        estimate = task.estimated_time if task.estimated_time is not None else 0
        consumed += estimate
        fits = consumed <= available_minutes
        planned_tasks.append(
            PlannedTaskResult(
                id=task.id,
                title=task.title,
                estimated_time=task.estimated_time,
                priority=task.priority,
                deadline=task.deadline,
                fits=fits,
            )
        )

    return DailyPlanResult(
        date=target,
        available_minutes=available_minutes,
        planned_tasks=planned_tasks,
    )
