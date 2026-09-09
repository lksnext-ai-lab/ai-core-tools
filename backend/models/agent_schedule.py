"""Persistence models for durable, periodic agent executions."""

from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from croniter import croniter
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from db.database import Base


class AgentSchedule(Base):
    __tablename__ = "agent_schedule"

    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey("Agent.agent_id", ondelete="CASCADE"), nullable=False)
    # In the current domain an App is the workspace boundary used by the API.
    app_id = Column(Integer, ForeignKey("App.app_id", ondelete="CASCADE"), nullable=False)
    created_by = Column(Integer, ForeignKey("User.user_id"), nullable=False)
    orchestrator_schedule_name = Column(String(255), nullable=False, unique=True)
    cron_expression = Column(String(120), nullable=False)
    timezone = Column(String(64), nullable=False, default="UTC", server_default="UTC")
    input_context = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False, default="active", server_default="active")
    max_concurrent_runs = Column(Integer, nullable=False, default=1, server_default="1")
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    agent = relationship("Agent")
    app = relationship("App")
    runs = relationship("AgentRunSummary", back_populates="schedule", cascade="all, delete-orphan")

    @property
    def next_run_at(self) -> Optional[datetime]:
        """Return the next scheduled instant in UTC for the user-facing API."""
        if self.status != "active":
            return None
        try:
            timezone = ZoneInfo(self.timezone)
            return croniter(self.cron_expression, datetime.now(timezone)).get_next(datetime).astimezone(ZoneInfo("UTC"))
        except (TypeError, ValueError, KeyError):
            return None


class AgentRunSummary(Base):
    __tablename__ = "agent_run_summary"
    __table_args__ = (Index("ix_agent_run_summary_schedule", "agent_schedule_id", "scheduled_time"),)

    id = Column(Integer, primary_key=True)
    agent_schedule_id = Column(
        Integer, ForeignKey("agent_schedule.id", ondelete="CASCADE"), nullable=False
    )
    orchestrator_run_id = Column(String(255), nullable=False)
    scheduled_time = Column(DateTime(timezone=True), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False)
    attempt_count = Column(Integer, nullable=False, default=0, server_default="0")
    error_summary = Column(Text, nullable=True)
    output_summary = Column(JSON, nullable=True)

    schedule = relationship("AgentSchedule", back_populates="runs")
