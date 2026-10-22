"""Commitment API router.

Exposes the commitment CRUD endpoints from Design §6, wiring the Pydantic
schemas (`app/schemas/commitment.py`) to the commitment service
(`app/services/commitment_service.py`). Each request builds a
:class:`CommitmentService` backed by a :class:`CommitmentRepository` bound to
the per-request session provided by the ``get_db`` dependency
(`app/data/database.py`).

Error handling is centralized (`app/api/errors.py`): the router does not catch
exceptions itself. Missing ids raise :class:`CommitmentNotFoundError`, which
the registered handler serializes into the ``404`` ``not_found`` envelope; body
validation failures raise FastAPI's ``RequestValidationError``, serialized into
the ``422`` ``validation_error`` envelope; and a partial update that would
invert the interval raises :class:`InvalidCommitmentIntervalError`, also
serialized into the ``422`` ``validation_error`` envelope. The endpoints
therefore read as a thin, declarative mapping from HTTP verbs to service calls.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.data.commitment_repository import CommitmentRepository
from app.data.database import get_db
from app.schemas.commitment import (
    CommitmentCreate,
    CommitmentRead,
    CommitmentUpdate,
)
from app.services.commitment_service import CommitmentService

router = APIRouter(prefix="/commitments", tags=["commitments"])


def get_commitment_service(db: Session = Depends(get_db)) -> CommitmentService:
    """Provide a :class:`CommitmentService` bound to the request-scoped session."""
    return CommitmentService(CommitmentRepository(db))


@router.post("", response_model=CommitmentRead, status_code=status.HTTP_201_CREATED)
def create_commitment(
    data: CommitmentCreate,
    service: CommitmentService = Depends(get_commitment_service),
) -> CommitmentRead:
    """Create a commitment and return it with ``201 Created``."""
    return service.create_commitment(data)


@router.get("", response_model=list[CommitmentRead])
def list_commitments(
    service: CommitmentService = Depends(get_commitment_service),
) -> list[CommitmentRead]:
    """Return all stored commitments."""
    return service.list_commitments()


@router.get("/{commitment_id}", response_model=CommitmentRead)
def get_commitment(
    commitment_id: int,
    service: CommitmentService = Depends(get_commitment_service),
) -> CommitmentRead:
    """Return a single commitment, or ``404`` when the id is missing."""
    return service.get_commitment(commitment_id)


@router.put("/{commitment_id}", response_model=CommitmentRead)
def update_commitment(
    commitment_id: int,
    data: CommitmentUpdate,
    service: CommitmentService = Depends(get_commitment_service),
) -> CommitmentRead:
    """Apply updates to a commitment.

    Returns ``404`` when the id is missing, or ``422`` when the resulting
    interval would be invalid (``end_time`` at or before ``start_time``).
    """
    return service.update_commitment(commitment_id, data)


@router.delete("/{commitment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_commitment(
    commitment_id: int,
    service: CommitmentService = Depends(get_commitment_service),
) -> None:
    """Delete a commitment (``204``), or ``404`` when the id is missing."""
    service.delete_commitment(commitment_id)
