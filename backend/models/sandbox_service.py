import enum
from sqlalchemy import Column, String, Integer, ForeignKey
from sqlalchemy.orm import relationship
from models.base_service import BaseService


class SandboxProviderEnum(enum.Enum):
    OpenSandbox = "opensandbox"
    Daytona = "daytona"
    E2B = "e2b"


class SandboxService(BaseService):
    """Per-app (or system-wide) sandbox provider credential configuration.

    Mirrors ``AIService``/``EmbeddingService``: reuses ``BaseService``'s
    ``endpoint``/``api_key``/``extra_config`` columns rather than adding
    first-class per-provider columns. ``extra_config`` holds each provider's
    non-secret tuning knobs as a JSON string (see
    ``tools.sandbox_service_utils``):

    - OpenSandbox: ``{"image": ...}``
    - Daytona: ``{"target": ..., "workspace": ..., "cpu": ..., "memory_gb": ...}``
    - E2B: ``{"template": ..., "workspace": ...}``
    """

    __tablename__ = 'SandboxService'

    provider = Column(String(45), nullable=False)
    app_id = Column(Integer, ForeignKey('App.app_id'), nullable=True)  # NULL = system/platform-wide
    app = relationship('App', back_populates='sandbox_services', foreign_keys=[app_id])
