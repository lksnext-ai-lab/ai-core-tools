from typing import Optional, List
from sqlalchemy.orm import Session
from models.app import App
from models.app_collaborator import AppCollaborator, CollaborationStatus
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)

class AppRepository:
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_by_id(self, app_id: int) -> Optional[App]:
        """Get a specific app by ID"""
        return self.db.query(App).filter(App.app_id == app_id).first()
    
    def get_by_owner(self, user_id: int) -> List[App]:
        """Get apps owned by a specific user ordered by creation date"""
        return self.db.query(App)\
            .filter(App.owner_id == user_id)\
            .order_by(App.create_date.desc())\
            .all()
    
    def get_collaborated_apps(self, user_id: int) -> List[AppCollaborator]:
        """Get apps where user is an accepted collaborator"""
        from sqlalchemy.orm import joinedload
        return self.db.query(AppCollaborator)\
            .filter(
                AppCollaborator.user_id == user_id,
                AppCollaborator.status == CollaborationStatus.ACCEPTED
            )\
            .options(joinedload(AppCollaborator.app))\
            .all()
    
    def create(self, app_data: dict) -> App:
        """Create a new app"""
        app = App()
        app.create_date = datetime.now()
        self._update_app_fields(app, app_data)
        
        self.db.add(app)
        self.db.commit()
        self.db.refresh(app)
        return app
    
    def update(self, app: App, app_data: dict) -> App:
        """Update an existing app"""
        self._update_app_fields(app, app_data)
        
        self.db.add(app)
        self.db.commit()
        self.db.refresh(app)
        return app
    
    def delete(self, app: App) -> bool:
        """Delete an app"""
        try:
            self.db.delete(app)
            self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error deleting app {app.app_id}: {e}")
            self.db.rollback()
            return False
    
    def _update_app_fields(self, app: App, data: dict):
        """Update app attributes with the provided data"""
        if 'name' in data:
            app.name = data['name']
        if 'owner_id' in data:
            app.owner_id = data['owner_id']
        if 'langsmith_api_key' in data:
            app.langsmith_api_key = data['langsmith_api_key']
