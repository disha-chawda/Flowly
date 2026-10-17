from sqlalchemy.orm import Session
from app.data.models import Commitment


class CommitmentRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, commitment: Commitment):
        self.db.add(commitment)
        self.db.commit()
        self.db.refresh(commitment)
        return commitment

    def get_by_id(self, commitment_id: int):
        return self.db.get(Commitment, commitment_id)

    def list(self):
        return self.db.query(Commitment).all()

    def update(self, commitment: Commitment):
        updated_commitment = self.db.merge(commitment)
        self.db.commit()
        self.db.refresh(updated_commitment)
        return updated_commitment

    def discard(self, commitment: Commitment):
        """Drop any pending in-memory changes to ``commitment``.

        Expires the instance so unflushed attribute mutations are forgotten and
        the next access reloads the stored values. Used to roll back a rejected
        update without committing the inverted state.
        """
        self.db.expire(commitment)

    def delete(self, commitment: Commitment):
        self.db.delete(commitment)
        self.db.commit()
