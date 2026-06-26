from sqlalchemy import Column, Integer, String, DateTime, Text
from db.database import Base
from datetime import datetime

class BaseService(Base):
    __abstract__ = True
    
    service_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    create_date = Column(DateTime, default=datetime.now)
    endpoint = Column(String(255), nullable=True)
    api_key = Column(Text, nullable=True)
    description = Column(String(1000), nullable=True)
    api_version = Column(String(50), nullable=True)
    # Provider-specific configuration that does not fit the standard
    # columns above, stored as a JSON object. Used by providers whose
    # access requires more than a single api_key — e.g. AWS Bedrock keeps
    # {"aws_access_key_id": ..., "aws_region": ...} here while the secret
    # access key reuses the masked `api_key` column.
    extra_config = Column(Text, nullable=True)