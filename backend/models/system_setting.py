from sqlalchemy import Column, String, Text, DateTime
from db.database import Base
from datetime import datetime


class SystemSetting(Base):
    """System-wide configuration settings model
    
    Settings are identified by a unique key and store typed values.
    The type field indicates how to interpret the value string.
    Settings are resolved from env vars first, then database, then defaults.
    """
    __tablename__ = 'system_settings'

    key = Column(String(100), primary_key=True, nullable=False)
    value = Column(Text, nullable=True)  # Null means "use default"
    type = Column(String(20), nullable=False, default='string')  # string, integer, boolean, float, json, string_list
    category = Column(String(50), nullable=False, default='general')  # UI grouping (marketplace, limits, general, etc.)
    description = Column(String(500), nullable=True)  # Human-readable description
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
