"""Application-scoped output destinations and their durable delivery outbox."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from db.database import Base


class OutputDestination(Base):
    __tablename__ = "output_destination"
    __table_args__ = (UniqueConstraint("app_id", "name", name="uq_output_destination_app_name"),)

    id = Column(Integer, primary_key=True)
    app_id = Column(Integer, ForeignKey("App.app_id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    provider_key = Column(String(80), nullable=False, default="teams_workflow", server_default="teams_workflow")
    content_mode = Column(String(30), nullable=False, default="result", server_default="result")
    public_config = Column(JSON, nullable=False, default=dict, server_default="{}")
    # Same app database record as the destination; never returned from API responses.
    webhook_url = Column(Text, nullable=False)
    credentials = Column(JSON, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True, server_default="true")
    created_by = Column(Integer, ForeignKey("User.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, server_default="now()")
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, server_default="now()")

    bindings = relationship("ScheduledTaskOutputBinding", back_populates="destination", cascade="all, delete-orphan")


class ScheduledTaskOutputBinding(Base):
    __tablename__ = "scheduled_task_output_binding"
    __table_args__ = (UniqueConstraint("scheduled_task_id", "destination_id", name="uq_task_output_destination"),)

    id = Column(Integer, primary_key=True)
    scheduled_task_id = Column(Integer, ForeignKey("scheduled_task.id", ondelete="CASCADE"), nullable=False, index=True)
    destination_id = Column(Integer, ForeignKey("output_destination.id", ondelete="CASCADE"), nullable=False, index=True)
    enabled = Column(Boolean, nullable=False, default=True, server_default="true")
    event_types = Column(JSON, nullable=False, default=lambda: ["succeeded"], server_default='["succeeded"]')
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, server_default="now()")

    task = relationship("ScheduledTask", back_populates="output_bindings")
    destination = relationship("OutputDestination", back_populates="bindings")
    deliveries = relationship("OutputDelivery", back_populates="binding", cascade="all, delete-orphan")


class OutputDelivery(Base):
    __tablename__ = "output_delivery"
    __table_args__ = (
        UniqueConstraint("run_id", "binding_id", "event_type", name="uq_output_delivery_run_binding_event"),
        Index("ix_output_delivery_dispatch", "status", "next_attempt_at"),
    )

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("scheduled_task_run.id", ondelete="CASCADE"), nullable=False, index=True)
    binding_id = Column(Integer, ForeignKey("scheduled_task_output_binding.id", ondelete="CASCADE"), nullable=False, index=True)
    destination_id = Column(Integer, ForeignKey("output_destination.id", ondelete="SET NULL"), nullable=True)
    event_type = Column(String(30), nullable=False, default="succeeded", server_default="succeeded")
    # Immutable public destination settings and card body; credentials are deliberately absent.
    destination_snapshot = Column(JSON, nullable=False, default=dict, server_default="{}")
    payload = Column(JSON, nullable=False, default=dict, server_default="{}")
    request_body = Column(LargeBinary, nullable=True)
    request_body_path = Column(Text, nullable=True)
    request_body_size = Column(Integer, nullable=True)
    request_body_sha256 = Column(String(64), nullable=True)
    status = Column(String(20), nullable=False, default="pending", server_default="pending", index=True)
    attempt_count = Column(Integer, nullable=False, default=0, server_default="0")
    dispatch_generation = Column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    lease_until = Column(DateTime, nullable=True)
    receipt = Column(JSON, nullable=True)
    error_summary = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, server_default="now()")
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, server_default="now()")

    run = relationship("ScheduledTaskRun", back_populates="output_deliveries")
    binding = relationship("ScheduledTaskOutputBinding", back_populates="deliveries")
    destination = relationship("OutputDestination")
    attempts = relationship("OutputDeliveryAttempt", back_populates="delivery", cascade="all, delete-orphan", order_by="OutputDeliveryAttempt.id")


class OutputArtifact(Base):
    __tablename__ = "output_artifact"
    __table_args__ = (UniqueConstraint("run_id", "file_id", name="uq_output_artifact_run_file"),)

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("scheduled_task_run.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = Column(String(255), nullable=False)
    filename = Column(String(512), nullable=False)
    content_type = Column(String(255), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    object_key = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, server_default="now()")


class OutputDeliveryAttempt(Base):
    __tablename__ = "output_delivery_attempt"

    id = Column(Integer, primary_key=True)
    delivery_id = Column(Integer, ForeignKey("output_delivery.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_number = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="sending", server_default="sending")
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow, server_default="now()")
    finished_at = Column(DateTime, nullable=True)
    http_status = Column(Integer, nullable=True)
    error_summary = Column(Text, nullable=True)

    delivery = relationship("OutputDelivery", back_populates="attempts")
