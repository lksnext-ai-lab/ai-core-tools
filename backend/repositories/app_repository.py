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
        if 'agent_rate_limit' in data:
            app.agent_rate_limit = data['agent_rate_limit']
        if 'max_file_size_mb' in data:
            app.max_file_size_mb = data['max_file_size_mb']
        if 'agent_cors_origins' in data:
            app.agent_cors_origins = data['agent_cors_origins']
    
    # Methods to get related entities for cascade deletion
    
    def get_agents_by_app_id(self, app_id: int):
        """Get all agents for an app"""
        from models.agent import Agent
        return self.db.query(Agent).filter(Agent.app_id == app_id).all()
    
    def get_repositories_by_app_id(self, app_id: int):
        """Get all repositories for an app"""
        from models.repository import Repository
        return self.db.query(Repository).filter(Repository.app_id == app_id).all()
    
    def get_domains_by_app_id(self, app_id: int):
        """Get all domains for an app"""
        from models.domain import Domain
        return self.db.query(Domain).filter(Domain.app_id == app_id).all()
    
    def get_silos_by_app_id(self, app_id: int):
        """Get all silos for an app"""
        from models.silo import Silo
        return self.db.query(Silo).filter(Silo.app_id == app_id).all()
    
    def get_output_parsers_by_app_id(self, app_id: int):
        """Get all output parsers for an app"""
        from models.output_parser import OutputParser
        return self.db.query(OutputParser).filter(OutputParser.app_id == app_id).all()
    
    def get_mcp_configs_by_app_id(self, app_id: int):
        """Get all MCP configs for an app"""
        from models.mcp_config import MCPConfig
        return self.db.query(MCPConfig).filter(MCPConfig.app_id == app_id).all()
    
    def get_api_keys_by_app_id(self, app_id: int):
        """Get all API keys for an app"""
        from models.api_key import APIKey
        return self.db.query(APIKey).filter(APIKey.app_id == app_id).all()
    
    def get_ai_services_by_app_id(self, app_id: int):
        """Get all AI services for an app"""
        from models.ai_service import AIService
        return self.db.query(AIService).filter(AIService.app_id == app_id).all()
    
    def get_embedding_services_by_app_id(self, app_id: int):
        """Get all embedding services for an app"""
        from models.embedding_service import EmbeddingService
        return self.db.query(EmbeddingService).filter(EmbeddingService.app_id == app_id).all()
    
    def get_urls_by_domain_id(self, domain_id: int):
        """Get all URLs for a domain"""
        from models.url import Url
        return self.db.query(Url).filter(Url.domain_id == domain_id).all()

    def get_skills_by_app_id(self, app_id: int):
        """Get all skills for an app"""
        from models.skill import Skill
        return self.db.query(Skill).filter(Skill.app_id == app_id).all()

    def get_mcp_servers_by_app_id(self, app_id: int):
        """Get all MCP servers for an app"""
        from models.mcp_server import MCPServer
        return self.db.query(MCPServer).filter(MCPServer.app_id == app_id).all()
