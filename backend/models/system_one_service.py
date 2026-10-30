from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship
from models.base_service import BaseService
from models.service_lifecycle import ServiceLifecycleMixin


class SystemOneService(ServiceLifecycleMixin, BaseService):
    """Per-app connection to a System One server.

    Reuses BaseService: ``endpoint`` = base URL, ``api_key`` = optional Bearer token,
    ``description`` = model name , ``extra_config`` = JSON string
    ``{"max_concurrency": int}``. v1 evaluates TEXT only (images are future work).
    """

    __tablename__ = 'SystemOneService'

    app_id = Column(Integer, ForeignKey('App.app_id'), nullable=False)
    app = relationship('App', back_populates='system_one_services', foreign_keys=[app_id])
