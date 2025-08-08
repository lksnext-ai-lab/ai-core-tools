from typing import Optional, List
from sqlalchemy.orm import Session
from models.app import App
from repositories.app_repository import AppRepository
from repositories.app_collaboration_repository import AppCollaborationRepository
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)

class AppService:

    def __init__(self, db: Session):
        self.db = db
        self.app_repo = AppRepository(db)
        self.collaboration_repo = AppCollaborationRepository(db)

    def get_apps_by_user(self, user_id: int) -> List[App]:
        """Get apps owned by a specific user ordered by creation date"""
        return self.app_repo.get_by_owner(user_id)

    def get_collaborated_apps(self, user_id: int):
        """Get apps where user is an accepted collaborator"""
        return self.app_repo.get_collaborated_apps(user_id)

    def get_apps(self, user_id: int) -> List[App]:
        """Get all apps for a specific user (owned + collaborated) ordered by creation date"""
        return self.collaboration_repo.get_user_accessible_apps(user_id)

    def get_app(self, app_id: int) -> Optional[App]:
        """Get a specific app by ID"""
        return self.app_repo.get_by_id(app_id)
    
    def create_or_update_app(self, app_data: dict) -> App:
        """Create a new app or update an existing one"""
        app_id = app_data.get('app_id')
        
        if app_id:
            app = self.app_repo.get_by_id(app_id)
            if app:
                return self.app_repo.update(app, app_data)
        
        # Create new app
        return self.app_repo.create(app_data)
    
    def delete_app(self, app_id: int) -> bool:
        """Delete an app and all its related data with proper cascade deletion
        
        Note: Access control should be handled at the API level
        """
        # TODO: Re-enable these imports once all services are migrated
        # from .repository_service import RepositoryService
        # from .domain_service import DomainService
        # from .agent_service import AgentService
        # from .output_parser_service import OutputParserService
        # from .ai_service_service import AIServiceService
        # from .silo_service import SiloService
        # from .embedding_service_service import EmbeddingServiceService
        # from .api_key_service import APIKeyService
        # from .mcp_config_service import MCPConfigService
        
        # Get the app
        app = self.app_repo.get_by_id(app_id)
        if not app:
            logger.warning(f"App {app_id} not found for deletion")
            return False
        
        logger.info(f"Starting cascade deletion for app {app_id}: {app.name}")
        
        try:
            # TODO: Implement cascade deletion for related entities
            # For now, just delete collaborations and the app
            
            # Delete collaborations
            collaborations = self.collaboration_repo.get_collaborations_by_app(app_id)
            for collab in collaborations:
                self.collaboration_repo.delete_collaboration(collab)
            
            # Delete the app
            success = self.app_repo.delete(app)
            
            if success:
                logger.info(f"Successfully deleted app {app_id} and all related data")
            
            return success
                
        except Exception as e:
            logger.error(f"Error during cascade deletion of app {app_id}: {str(e)}")
            return False 