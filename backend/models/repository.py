from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime
import config

class Repository(Base):
    __tablename__ = 'Repository'
    repository_id = Column(Integer, primary_key=True)
    name = Column(String(255))
    create_date = Column(DateTime, default=datetime.now)
    type = Column(String(45))
    status = Column(String(45))
    app_id = Column(Integer,
                        ForeignKey('App.app_id'),
                        nullable=True)

    app = relationship('App',
                           back_populates='repositories',
                           foreign_keys=[app_id])
    
    resources = relationship('Resource', lazy=True)
    folders = relationship('Folder', back_populates='repository', cascade='all, delete-orphan')

    silo = relationship('Silo', lazy=False, uselist=False)
    silo_id = Column(Integer, ForeignKey('Silo.silo_id'), nullable=False)

    def get_embedding_service(self):
        """
        Returns the embedding service associated with this repository's silo
        """
        if self.silo and self.silo.embedding_service:
            return self.silo.embedding_service
        return None

    def to_dict(self, include_relationships=False):
        vector_db_type = None
        if self.silo and getattr(self.silo, 'vector_db_type', None):
            vector_db_type = self.silo.vector_db_type
        else:
            default_type = config.VECTOR_DB_TYPE or 'PGVECTOR'
            vector_db_type = default_type.upper() if isinstance(default_type, str) else default_type

        data = {
            'repository_id': self.repository_id,
            'name': self.name,
            'type': self.type,
            'status': self.status,
            'vector_db_type': vector_db_type,
            'app_id': self.app_id,
            'silo_id': self.silo_id
        }
        
        if include_relationships:
            if self.silo:
                data['silo'] = {
                    'silo_id': self.silo.silo_id,
                    'embedding_service': self.silo.embedding_service.name if self.silo.embedding_service else None
                }
            data['resources'] = [{
                'resource_id': resource.resource_id,
                # Add other resource fields as needed
            } for resource in self.resources]
        
        return data 