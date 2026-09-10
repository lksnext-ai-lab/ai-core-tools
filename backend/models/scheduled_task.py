"""First-class scheduled tasks and their conversation-backed executions."""

from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from croniter import croniter
from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from db.database import Base


class ScheduledTask(Base):
    __tablename__ = "scheduled_task"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    agent_id = Column(Integer, ForeignKey("Agent.agent_id", ondelete="CASCADE"), nullable=False)
    app_id = Column(Integer, ForeignKey("App.app_id", ondelete="CASCADE"), nullable=False)
    created_by = Column(Integer, ForeignKey("User.user_id"), nullable=False)
    orchestrator_schedule_name = Column(String(255), nullable=False, unique=True)
    input = Column(JSON, nullable=False, default=dict, server_default="{}")
    cron_expression = Column(String(120), nullable=False)
    timezone = Column(String(64), nullable=False, default="UTC", server_default="UTC")
    conversation_mode = Column(String(20), nullable=False, default="new_per_run", server_default="new_per_run")
    persistent_conversation_id = Column(Integer, ForeignKey("Conversation.conversation_id"), nullable=True)
    status = Column(String(20), nullable=False, default="active", server_default="active")
    max_concurrent_runs = Column(Integer, nullable=False, default=1, server_default="1")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, server_default="now()")
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, server_default="now()")

    runs = relationship("ScheduledTaskRun", back_populates="task", cascade="all, delete-orphan")

    @property
    def next_run_at(self) -> Optional[datetime]:
        if self.status != "active":
            return None
        try:
            timezone = ZoneInfo(self.timezone)
            return croniter(self.cron_expression, datetime.now(timezone)).get_next(datetime).astimezone(ZoneInfo("UTC"))
        except (TypeError, ValueError, KeyError):
            return None


class ScheduledTaskRun(Base):
    __tablename__ = "scheduled_task_run"
    __table_args__ = (Index("ix_scheduled_task_run_task", "scheduled_task_id", "scheduled_time"),)

    id = Column(Integer, primary_key=True)
    scheduled_task_id = Column(Integer, ForeignKey("scheduled_task.id", ondelete="CASCADE"), nullable=False)
    conversation_id = Column(Integer, ForeignKey("Conversation.conversation_id"), nullable=True)
    conversation_anchor_message_id = Column(Integer, nullable=True)
    orchestrator_run_id = Column(String(255), nullable=False)
    scheduled_time = Column(DateTime, nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False, default="queued", server_default="queued")
    attempt_count = Column(Integer, nullable=False, default=0, server_default="0")
    error_summary = Column(Text, nullable=True)

    task = relationship("ScheduledTask", back_populates="runs")
