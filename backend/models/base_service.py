from sqlalchemy import Column, Integer, String, DateTime
from db.database import Base
from datetime import datetime

class BaseService(Base):
    __abstract__ = True
    
    service_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    create_date = Column(DateTime, default=datetime.now)
    endpoint = Column(String(255), nullable=True)
    api_key = Column(String(255), nullable=True)
    description = Column(String(1000), nullable=True)
    api_version = Column(String(50), nullable=True) 