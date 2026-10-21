"""Dashboard service layer.

Orchestrates the read-side dashboard use cases described in Design 7 and
Requirements 12-15: the Today view, the Upcoming view, the workload summary,
and the daily plan.

The service loads tasks and commitments through the repositories, filters them
to the set relevant to the requested date, and - for the workload and daily
plan - delegates the actual calculation to the pure planning core
(`app/planning/workload.py` 8, `app/planning/daily_plan.py` 9). The pure
functions do no I/O; the service is the layer that reads from storage and feeds
them already-loaded plain objects.

Filtering rules (Design 7, 8, 9; Requirements 12, 13, 14, 15):
    * Today view - all tasks whose deadline falls on the target calendar date,
      INCLUDING completed ones. Completed tasks stay in the list and remain
      distinguishable through their ``completion`` field so the API can label
      them complete (Requirement 12.1-12.3).
    * Upcoming view - incomplete tasks whose deadline falls strictly after the
      target date, ordered by deadline ascending (Requirement 13).
    * Workload - the day's incomplete tasks due ON the target date plus the
      commitments that overlap that date, handed to ``compute_workload``
      (Requirement 14.4, Design 8).
    * Daily plan - the incomplete tasks handed to ``generate_daily_plan`` with
      the available minutes from the workload calculation (Requirement 15,
      Design 9). Candidate selection (deadline on or before the date, no-deadline
      excluded) is the pure function's responsibility.

Validation lives in the Pydantic schemas, so this service only reads. It stays
framework-agnostic and returns the plain planning-core results and ORM entities;
the API layer maps them onto the Pydantic response models in
`app/schemas/dashboard.py`.
"""

from datetime import date as date_type, datetime, time, timedelta

from app.data.commitment_repository import CommitmentRepository
from app.data.models import Commitment, Task
from app.data.task_repository import TaskRepository
from app.domain.enums import Completion
from app.planning.daily_plan import DailyPlanResult, generate_daily_plan
from app.planning.workload import WorkloadResult, compute_workload


def _as_date(value) -> date_type:
    """Return the ``date`` component of a ``date`` or ``datetime`` value."""
    if isinstance(value, datetime):
        return value.date()
    return value


def _is_incomplete(task: Task) -> bool:
    """Return whether a task is still incomplete."""
    return task.completion == Completion.INCOMPLETE


def _commitment_overlaps_date(commitment: Commitment, target_date: date_type) -> bool:
    """Return whether a commitment overlaps the target calendar date.

    The workload window spans ``[00:00, 16:00)`` of the target date. A commitment
    is relevant to that date when its ``[start_time, end_time)`` interval overlaps
    the whole calendar day ``[00:00, next-midnight)``. Commitments wholly on other
    days are excluded so they cannot leak minutes into this date's workload.
    """
    day_start = datetime.combine(target_date, time.min)
    day_end = day_start + timedelta(days=1)
    return commitment.start_time < day_end and commitment.end_time > day_start


class DashboardService:
    def __init__(
        self,
        task_repository: TaskRepository,
        commitment_repository: CommitmentRepository,
    ):
        self.task_repository = task_repository
        self.commitment_repository = commitment_repository

    def today_view(self, target: date_type) -> list[Task]:
        """Return every task whose deadline falls on ``target`` (Requirement 12).

        Includes completed tasks as well as incomplete ones: Requirement 12.1
        returns all tasks due on the current calendar date, and 12.3 requires
        completed tasks to stay in the result labeled complete. Completion state
        is preserved on each returned task via its ``completion`` field so the
        API layer can mark finished work as done.

        Tasks without a deadline are not tied to a specific day and are excluded.
        Ordered by deadline ascending, then id, for a deterministic result.
        """
        target_date = _as_date(target)
        tasks = [
            task
            for task in self.task_repository.list()
            if task.deadline is not None
            and _as_date(task.deadline) == target_date
        ]
        tasks.sort(key=lambda task: (task.deadline, task.id))
        return tasks

    def upcoming_view(self, target: date_type) -> list[Task]:
        """Return incomplete tasks with future deadlines (Requirement 13).

        Selects incomplete tasks whose deadline falls strictly after the target
        calendar date, ordered by deadline ascending so approaching work surfaces
        first. Completed tasks and tasks without a deadline are excluded.
        """
        target_date = _as_date(target)
        tasks = [
            task
            for task in self.task_repository.list()
            if _is_incomplete(task)
            and task.deadline is not None
            and _as_date(task.deadline) > target_date
        ]
        tasks.sort(key=lambda task: task.deadline)
        return tasks

    def _incomplete_tasks_due_on(self, target_date: date_type) -> list[Task]:
        """Return incomplete tasks whose deadline falls ON ``target_date``.

        This is the task set the workload calculation operates over: Requirement
        14.4 and Design 8 both scope the estimated-time sum to incomplete tasks
        whose deadline falls on that date (an exact match, not overdue work).
        """
        return [
            task
            for task in self.task_repository.list()
            if _is_incomplete(task)
            and task.deadline is not None
            and _as_date(task.deadline) == target_date
        ]

    def _commitments_on(self, target_date: date_type) -> list[Commitment]:
        """Return the commitments that overlap ``target_date``.

        Filters out commitments belonging to other days so they cannot
        contribute minutes to this date's workload (Requirement 14.2).
        """
        return [
            commitment
            for commitment in self.commitment_repository.list()
            if _commitment_overlaps_date(commitment, target_date)
        ]

    def workload(self, target: date_type) -> WorkloadResult:
        """Compute the workload summary for ``target`` (Design 8).

        Loads the day's incomplete tasks due on the date and the commitments
        that overlap the date, then delegates to the pure ``compute_workload``
        function. Commitments from other days are excluded here so only this
        date's obligations count toward committed time.
        """
        target_date = _as_date(target)
        tasks = self._incomplete_tasks_due_on(target_date)
        commitments = self._commitments_on(target_date)
        return compute_workload(target_date, tasks, commitments)

    def daily_plan(self, target: date_type) -> DailyPlanResult:
        """Generate the deterministic daily plan for ``target`` (Design 9).

        Derives the available minutes from the workload calculation, loads all
        incomplete tasks, and delegates candidate selection, ordering, and fit
        annotation to the pure ``generate_daily_plan`` function.
        """
        target_date = _as_date(target)
        available_minutes = self.workload(target_date).available_minutes
        incomplete_tasks = [
            task for task in self.task_repository.list() if _is_incomplete(task)
        ]
        return generate_daily_plan(target_date, incomplete_tasks, available_minutes)
