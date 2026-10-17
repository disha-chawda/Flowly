"""Task service layer.

Orchestrates the task use cases (create, edit, delete, complete) described in
Design §7. The service applies defaults, delegates persistence to the task
repository (each repository call is a single transaction), raises a not-found
condition when a referenced id is missing, and returns the stored entities.

Validation lives in the Pydantic schemas (Design §10), so the service receives
already-validated payloads. The service stays framework-agnostic: it raises a
plain :class:`TaskNotFoundError` for missing ids, which the API error handlers
(`app/api/errors.py`) map to a `404` response.
"""

from app.data.models import Task
from app.data.task_repository import TaskRepository
from app.domain.enums import Completion
from app.schemas.task import TaskCreate, TaskUpdate


class TaskNotFoundError(Exception):
    """Raised when a task id does not exist in storage."""

    def __init__(self, task_id: int):
        self.task_id = task_id
        super().__init__(f"Task {task_id} not found")


class TaskService:
    def __init__(self, repository: TaskRepository):
        self.repository = repository

    def create_task(self, data: TaskCreate) -> Task:
        """Create a task, applying defaults for any unspecified fields."""
        task = Task(
            title=data.title,
            description=data.description,
            deadline=data.deadline,
            estimated_time=data.estimated_time,
            priority=data.priority,
            category=data.category,
            completion=data.completion,
            source=data.source,
        )
        return self.repository.create(task)

    def get_task(self, task_id: int) -> Task:
        """Return the stored task or raise if the id is missing."""
        task = self.repository.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        return task

    def list_tasks(self) -> list[Task]:
        """Return all stored tasks."""
        return self.repository.list()

    def update_task(self, task_id: int, data: TaskUpdate) -> Task:
        """Apply the provided updates to an existing task.

        Only fields explicitly supplied in ``data`` are changed; omitted fields
        are left untouched. Raises :class:`TaskNotFoundError` when the id is
        missing.
        """
        task = self.get_task(task_id)
        updates = data.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(task, field, value)
        return self.repository.update(task)

    def delete_task(self, task_id: int) -> None:
        """Delete an existing task, raising if the id is missing."""
        task = self.get_task(task_id)
        self.repository.delete(task)

    def set_completion(self, task_id: int, completion: Completion) -> Task:
        """Set a task's completion state, raising if the id is missing."""
        task = self.get_task(task_id)
        return self.repository.set_completion(task, completion)
