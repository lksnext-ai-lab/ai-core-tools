from sqlalchemy import Column, DateTime, String

DEPRECATION_NOTICE_MAX_LENGTH = 1000


class ServiceLifecycleMixin:
    """Planned end of service. Status (active/deprecated/retired) is computed at read time."""

    end_of_service_at = Column(DateTime(timezone=True), nullable=True)
    deprecation_notice = Column(String(DEPRECATION_NOTICE_MAX_LENGTH), nullable=True)
