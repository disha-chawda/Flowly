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

    def delete(self, commitment: Commitment):
        self.db.delete(commitment)
        self.db.commit()
