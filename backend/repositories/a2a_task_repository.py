from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from models.a2a_task import A2ATask


class A2ATaskRepository:
    """Repository for persisted A2A task state."""

    @staticmethod
    def get_by_id(db: Session, task_id: str) -> Optional[A2ATask]:
        return db.query(A2ATask).filter(A2ATask.task_id == task_id).first()

    @staticmethod
    def save(db: Session, task: A2ATask) -> A2ATask:
        task.updated_at = datetime.utcnow()
        db.add(task)
        db.commit()
        db.refresh(task)
        return task

    @staticmethod
    def delete(db: Session, task: A2ATask) -> None:
        db.delete(task)
        db.commit()
