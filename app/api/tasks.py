"""Task API router.

Exposes the task CRUD + completion endpoints from Design §6, wiring the
Pydantic schemas (`app/schemas/task.py`) to the task service
(`app/services/task_service.py`). Each request builds a :class:`TaskService`
backed by a :class:`TaskRepository` bound to the per-request session provided by
the ``get_db`` dependency (`app/data/database.py`).

Error handling is centralized (`app/api/errors.py`): the router does not catch
exceptions itself. Missing ids raise :class:`TaskNotFoundError`, which the
registered handler serializes into the ``404`` ``not_found`` envelope, and body
validation failures raise FastAPI's ``RequestValidationError``, serialized into
the ``422`` ``validation_error`` envelope. The endpoints therefore read as a
thin, declarative mapping from HTTP verbs to service calls.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.data.database import get_db
from app.data.task_repository import TaskRepository
from app.domain.enums import Completion
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate
from app.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])


class CompletionUpdate(BaseModel):
    """Request body for the completion-toggle endpoint.

    Restricting the payload to the :class:`Completion` enum means an invalid
    value is rejected by request validation (``422``) before the service is
    reached, consistent with the rest of the task schemas.
    """

    completion: Completion


def get_task_service(db: Session = Depends(get_db)) -> TaskService:
    """Provide a :class:`TaskService` bound to the request-scoped session."""
    return TaskService(TaskRepository(db))


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(
    data: TaskCreate, service: TaskService = Depends(get_task_service)
) -> TaskRead:
    """Create a task and return it with ``201 Created``."""
    return service.create_task(data)


@router.get("", response_model=list[TaskRead])
def list_tasks(service: TaskService = Depends(get_task_service)) -> list[TaskRead]:
    """Return all stored tasks."""
    return service.list_tasks()


@router.get("/{task_id}", response_model=TaskRead)
def get_task(
    task_id: int, service: TaskService = Depends(get_task_service)
) -> TaskRead:
    """Return a single task, or ``404`` when the id is missing."""
    return service.get_task(task_id)


@router.put("/{task_id}", response_model=TaskRead)
def update_task(
    task_id: int,
    data: TaskUpdate,
    service: TaskService = Depends(get_task_service),
) -> TaskRead:
    """Apply updates to a task, or ``404`` when the id is missing."""
    return service.update_task(task_id, data)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int, service: TaskService = Depends(get_task_service)
) -> None:
    """Delete a task (``204``), or ``404`` when the id is missing."""
    service.delete_task(task_id)


@router.patch("/{task_id}/completion", response_model=TaskRead)
def set_task_completion(
    task_id: int,
    data: CompletionUpdate,
    service: TaskService = Depends(get_task_service),
) -> TaskRead:
    """Set a task's completion state, or ``404`` when the id is missing."""
    return service.set_completion(task_id, data.completion)
