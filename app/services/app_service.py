from typing import Optional
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
class AppService:

    @staticmethod
    def get_apps(user_id: int) -> list[App]:
        """Get all apps for a specific user ordered by creation date"""
        return db.session.query(App)\
            .filter(App.user_id == user_id)\
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
        """Update app attributes"""
        app.name = data['name']
        app.user_id = data['user_id']
        
    @staticmethod
    def delete_app(app_id: int):
        """Delete an app and all its related data"""
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
            
            # Finally delete the app itself
            db.session.delete(app)
            db.session.commit()