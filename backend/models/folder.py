from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime

class Folder(Base):
    __tablename__ = 'Folder'
    
    folder_id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    create_date = Column(DateTime, default=datetime.now)
    status = Column(String(45), default='active')
    
    # Foreign Keys
    repository_id = Column(Integer, ForeignKey('Repository.repository_id'), nullable=False)
    parent_folder_id = Column(Integer, ForeignKey('Folder.folder_id'), nullable=True)
    
    # Relationships
    repository = relationship('Repository', back_populates='folders', foreign_keys=[repository_id])
    parent_folder = relationship('Folder', remote_side=[folder_id], back_populates='subfolders', foreign_keys=[parent_folder_id])
    subfolders = relationship('Folder', back_populates='parent_folder', foreign_keys=[parent_folder_id], cascade='all, delete-orphan')
    resources = relationship('Resource', back_populates='folder', cascade='all, delete-orphan')
    
    def to_dict(self, include_children=False):
        """Convert folder to dictionary representation"""
        data = {
            'folder_id': self.folder_id,
            'name': self.name,
            'create_date': self.create_date,
            'status': self.status,
            'repository_id': self.repository_id,
            'parent_folder_id': self.parent_folder_id
        }
        
        if include_children:
            data['subfolders'] = [subfolder.to_dict() for subfolder in self.subfolders]
            data['resources'] = [{
                'resource_id': resource.resource_id,
                'name': resource.name,
                'uri': resource.uri,
                'type': resource.type
            } for resource in self.resources]
        
        return data
    
    def get_path(self):
        """Get the full path from root to this folder"""
        path_parts = []
        current = self
        while current is not None:
            path_parts.insert(0, current.name)
            current = current.parent_folder
        return '/'.join(path_parts)
    
    def __repr__(self):
        return f"<Folder(folder_id={self.folder_id}, name='{self.name}', repository_id={self.repository_id})>"

