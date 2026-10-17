"""Commitment service layer.

Orchestrates the commitment use cases (create, edit, delete) described in
Design §7 and Requirements §3.1–§3.3, §10. The service applies defaults
(``source=manual`` for created commitments), delegates persistence to the
commitment repository (each repository call is a single transaction), raises a
not-found condition when a referenced id is missing, and returns the stored
entities.

Validation lives in the Pydantic schemas (Design §10), so the service receives
already-validated payloads. The service stays framework-agnostic: it raises a
plain :class:`CommitmentNotFoundError` for missing ids, which the API error
handlers (`app/api/errors.py`) map to a `404` response.
"""

from app.data.commitment_repository import CommitmentRepository
from app.data.models import Commitment
from app.schemas.commitment import CommitmentCreate, CommitmentUpdate


class CommitmentNotFoundError(Exception):
    """Raised when a commitment id does not exist in storage."""

    def __init__(self, commitment_id: int):
        self.commitment_id = commitment_id
        super().__init__(f"Commitment {commitment_id} not found")


class CommitmentService:
    def __init__(self, repository: CommitmentRepository):
        self.repository = repository

    def create_commitment(self, data: CommitmentCreate) -> Commitment:
        """Create a commitment, applying ``source=manual`` from the payload."""
        commitment = Commitment(
            title=data.title,
            start_time=data.start_time,
            end_time=data.end_time,
            source=data.source,
        )
        return self.repository.create(commitment)

    def get_commitment(self, commitment_id: int) -> Commitment:
        """Return the stored commitment or raise if the id is missing."""
        commitment = self.repository.get_by_id(commitment_id)
        if commitment is None:
            raise CommitmentNotFoundError(commitment_id)
        return commitment

    def list_commitments(self) -> list[Commitment]:
        """Return all stored commitments."""
        return self.repository.list()

    def update_commitment(
        self, commitment_id: int, data: CommitmentUpdate
    ) -> Commitment:
        """Apply the provided updates to an existing commitment.

        Only fields explicitly supplied in ``data`` are changed; omitted fields
        are left untouched. Raises :class:`CommitmentNotFoundError` when the id
        is missing.
        """
        commitment = self.get_commitment(commitment_id)
        updates = data.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(commitment, field, value)
        return self.repository.update(commitment)

    def delete_commitment(self, commitment_id: int) -> None:
        """Delete an existing commitment, raising if the id is missing."""
        commitment = self.get_commitment(commitment_id)
        self.repository.delete(commitment)
