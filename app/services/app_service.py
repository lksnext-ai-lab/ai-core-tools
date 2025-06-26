from typing import Optional, List
from model.app import App
from extensions import db
from datetime import datetime
from services.silo_service import SiloService
from services.resource_service import ResourceService
from services.repository_service import RepositoryService
from services.domain_service import DomainService
from services.agent_service import AgentService
from services.output_parser_service import OutputParserService
from services.embedding_service_service import EmbeddingServiceService
from services.ai_service_service import AIServiceService
from services.api_key_service import APIKeyService
from services.mcp_config_service import MCPConfigService
from services.app_collaboration_service import AppCollaborationService
from utils.logger import get_logger

logger = get_logger(__name__)

class AppService:

    @staticmethod
    def get_apps(user_id: int) -> list[App]:
        """Get all apps for a specific user (owned + collaborated) ordered by creation date"""
        return AppCollaborationService.get_user_accessible_apps(user_id)

    @staticmethod
    def get_owned_apps(user_id: int) -> list[App]:
        """Get apps owned by a specific user ordered by creation date"""
        return db.session.query(App)\
            .filter(App.owner_id == user_id)\
            .order_by(App.create_date.desc())\
            .all()

    @staticmethod
    def get_app(app_id: int) -> Optional[App]:
        """Get a specific app by ID"""
        return db.session.query(App).filter(App.app_id == app_id).first()
    
    @staticmethod
    def create_or_update_app(app_data: dict) -> App:
        """Create a new app or update an existing one"""
        app_id = app_data.get('app_id')
        app = AppService.get_app(app_id) if app_id else None
        
        if not app:
            app = App()
            app.create_date = datetime.now()
        
        AppService._update_app(app, app_data)
        
        db.session.add(app)
        db.session.commit()
        db.session.refresh(app)
        return app
    
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
    def delete_app(app_id: int, user_id: int) -> bool:
        """Delete an app and all its related data (owner only)"""
        # Check if user can manage the app
        if not AppCollaborationService.can_user_manage_app(user_id, app_id):
            logger.warning(f"User {user_id} attempted to delete app {app_id} without permission")
            return False
        
        app = db.session.query(App).filter(App.app_id == app_id).first()
        if app:
            # Delete all repositories (this will also delete their resources)
            for repository in app.repositories:
                RepositoryService.delete_repository(repository)
            
            # Delete all domains and their URLs
            for domain in app.domains:
                DomainService.delete_domain(domain)
            
            # Delete all agents
            for agent in app.agents:
                AgentService.delete_agent(agent.agent_id)
            
            # Delete all output parsers
            for parser in app.output_parsers:
                OutputParserService().delete_parser(parser.parser_id)
            
            # Delete all AI services
            AIServiceService.delete_by_app_id(app.app_id)

            # Delete all silos
            for silo in app.silos:
                SiloService.delete_silo(silo.silo_id)

            # Delete all embedding services
            EmbeddingServiceService.delete_by_app_id(app.app_id)
            
            # Delete all API keys
            APIKeyService.delete_by_app_id(app.app_id)

            # Delete all MCP configs
            MCPConfigService.delete_by_app_id(app.app_id)
            
            # Delete all collaborations
            from model.app_collaborator import AppCollaborator
            collaborations = db.session.query(AppCollaborator).filter(AppCollaborator.app_id == app_id).all()
            for collab in collaborations:
                db.session.delete(collab)
            
            # Finally delete the app itself
            db.session.delete(app)
            db.session.commit()
            
            logger.info(f"App {app_id} deleted by user {user_id}")
            return True
        
        return False