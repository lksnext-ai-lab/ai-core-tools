from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey 
from sqlalchemy.orm import relationship
from app.db.base_class import Base


class Repository(Base):
    __tablename__ = 'Repository'
    repository_id = Column(Integer, primary_key=True)
    name = Column(String(255))
    type = Column(String(45))
    status = Column(String(45))
    app_id = Column(Integer,
                        ForeignKey('App.app_id'),
                        nullable=True)

    app = relationship('App',
                           back_populates='repositories',
                           foreign_keys=[app_id])
    
    resources = relationship('Resource', lazy=True)

    silo = relationship('Silo', lazy=False, uselist=False)
    silo_id = Column(Integer, ForeignKey('Silo.silo_id'), nullable=False)

    def to_dict(self, include_relationships=False):
        data = {
            'repository_id': self.repository_id,
            'name': self.name,
            'type': self.type,
            'status': self.status,
            'app_id': self.app_id,
            'silo_id': self.silo_id
        }
        
        if include_relationships:
            if self.silo:
                data['silo'] = {
                    'silo_id': self.silo.silo_id,
                    # Add other silo fields as needed
                }
            data['resources'] = [{
                'resource_id': resource.resource_id,
                # Add other resource fields as needed
            } for resource in self.resources]
        
        return data

