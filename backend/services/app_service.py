from typing import Optional, List
from models.app import App
from models.app_collaborator import AppCollaborator
from db.session import SessionLocal
from datetime import datetime
from services.app_collaboration_service import AppCollaborationService
# TODO: Re-enable these imports once all services are migrated
# from services.silo_service import SiloService
# from services.resource_service import ResourceService
# from services.repository_service import RepositoryService
# from services.domain_service import DomainService
# from services.agent_service import AgentService
# from services.output_parser_service import OutputParserService
# from services.embedding_service_service import EmbeddingServiceService
# from services.ai_service_service import AIServiceService
# from services.api_key_service import APIKeyService
# from services.mcp_config_service import MCPConfigService
from utils.logger import get_logger

logger = get_logger(__name__)

class AppService:

    @staticmethod
    def get_apps_by_user(user_id: int) -> List[App]:
        """Get apps owned by a specific user ordered by creation date"""
        session = SessionLocal()
        try:
            return session.query(App)\
                .filter(App.owner_id == user_id)\
                .order_by(App.create_date.desc())\
                .all()
        finally:
            session.close()

    @staticmethod
    def get_collaborated_apps(user_id: int) -> List[AppCollaborator]:
        """Get apps where user is an accepted collaborator"""
        session = SessionLocal()
        try:
            from sqlalchemy.orm import joinedload
            from models.app_collaborator import CollaborationStatus
            return session.query(AppCollaborator)\
                .filter(
                    AppCollaborator.user_id == user_id,
                    AppCollaborator.status == CollaborationStatus.ACCEPTED
                )\
                .options(joinedload(AppCollaborator.app))\
                .all()
        finally:
            session.close()

    @staticmethod
    def get_apps(user_id: int) -> List[App]:
        """Get all apps for a specific user (owned + collaborated) ordered by creation date"""
        return AppCollaborationService.get_user_accessible_apps(user_id)

    @staticmethod
    def get_app(app_id: int) -> Optional[App]:
        """Get a specific app by ID"""
        session = SessionLocal()
        try:
            return session.query(App).filter(App.app_id == app_id).first()
        finally:
            session.close()
    
    @staticmethod
    def create_or_update_app(app_data: dict) -> App:
        """Create a new app or update an existing one"""
        session = SessionLocal()
        try:
            app_id = app_data.get('app_id')
            app = None
            
            if app_id:
                app = session.query(App).filter(App.app_id == app_id).first()
            
            if not app:
                app = App()
                app.create_date = datetime.now()
            
            AppService._update_app(app, app_data)
            
            session.add(app)
            session.commit()
            session.refresh(app)
            return app
        finally:
            session.close()
    
    @staticmethod
    def _update_app(app: App, data: dict):
        """Update app attributes with the provided data.
        Only updates attributes that are present in the data dictionary.
        
        Args:
            app (App): The app instance to update
            data (dict): Dictionary containing the attributes to update
        """
        if 'name' in data:
            app.name = data['name']
        if 'owner_id' in data:
            app.owner_id = data['owner_id']

        if 'langsmith_api_key' in data:
            app.langsmith_api_key = data['langsmith_api_key']
        
    @staticmethod
    def delete_app(app_id: int) -> bool:
        """Delete an app and all its related data
        
        Note: Access control should be handled at the API level
        TODO: Implement cascade deletion of related entities once services are migrated
        """
        session = SessionLocal()
        try:
            app = session.query(App).filter(App.app_id == app_id).first()
            if not app:
                return False
            
            # TODO: Delete all related entities once services are migrated
            # - repositories and resources
            # - domains and URLs  
            # - agents
            # - output parsers
            # - AI services
            # - silos
            # - embedding services
            # - API keys
            # - MCP configs
            
            # Delete all collaborations
            collaborations = session.query(AppCollaborator).filter(AppCollaborator.app_id == app_id).all()
            for collab in collaborations:
                session.delete(collab)
            
            # Finally delete the app itself
            session.delete(app)
            session.commit()
            
            logger.info(f"App {app_id} deleted")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting app {app_id}: {str(e)}")
            session.rollback()
            return False
        finally:
            session.close() 