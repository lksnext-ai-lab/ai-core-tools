from sqlalchemy import Column, Integer, String
from db.base_class import Base

class BaseService(Base):
    __abstract__ = True
    
    service_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    endpoint = Column(String(255), nullable=True)
    api_key = Column(String(255), nullable=True)
    description = Column(String(1000), nullable=True)