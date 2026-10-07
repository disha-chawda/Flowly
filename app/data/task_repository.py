from sqlalchemy.orm import Session
from app.data.models import Task
from app.domain.enums import Completion

class TaskRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, task: Task):
        # the new task into the checkout basket.
        self.db.add(task)
        # actually clicking “Place order.”
        self.db.commit()
        self.db.refresh(task)
        # sends the finished Task object back to whoever called it.
        return task

    def get_by_id(self, task_id: int):
        # Using this database session, find the Task whose primary-key ID equals task_id.
        return self.db.get(Task, task_id)

    def list(self):
        return self.db.query(Task).all()
    # Find an existing task and change its information
    def update(self, task: Task):
        self.db.merge(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def delete(self, task: Task):
        self.db.delete(task)
        self.db.commit()
        
    def set_completion(self, task: Task, completion: Completion):
        task.completion = completion
        self.db.commit()
        self.db.refresh(task)
        return task



