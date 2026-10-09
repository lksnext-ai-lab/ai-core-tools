from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship
from models.base_service import BaseService


class SystemOneService(BaseService):
    """Per-app connection to a System One server.

    Reuses BaseService: ``endpoint`` = base URL, ``api_key`` = optional Bearer token,
    ``description`` = model name , ``extra_config`` = JSON string
    ``{"max_concurrency": int}``. v1 evaluates TEXT only (images are future work).
    """

    __tablename__ = 'SystemOneService'

    app_id = Column(Integer, ForeignKey('App.app_id'), nullable=False)
    app = relationship('App', back_populates='system_one_services', foreign_keys=[app_id])
