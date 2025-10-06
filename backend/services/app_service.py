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
        from .repository_service import RepositoryService
        from .domain_service import DomainService
        from .agent_service import AgentService
        from .output_parser_service import OutputParserService
        from .ai_service_service import AIServiceService
        from .silo_service import SiloService
        from .embedding_service_service import EmbeddingServiceService
        from .api_key_service import APIKeyService
        from .mcp_config_service import MCPConfigService
        from .resource_service import ResourceService
        from .url_service import UrlService
        
        # Get the app
        app = self.app_repo.get_by_id(app_id)
        if not app:
            logger.warning(f"App {app_id} not found for deletion")
            return False
        
        logger.info(f"Starting cascade deletion for app {app_id}: {app.name}")
        
        try:
            # Initialize all required services
            repository_service = RepositoryService()
            domain_service = DomainService()
            agent_service = AgentService()
            output_parser_service = OutputParserService()
            ai_service_service = AIServiceService()
            silo_service = SiloService()
            embedding_service_service = EmbeddingServiceService()
            api_key_service = APIKeyService()
            mcp_config_service = MCPConfigService()
            resource_service = ResourceService()
            url_service = UrlService()
            
            # Delete in the correct order to respect foreign key constraints
            
            # 1. Delete agents (they depend on AI services, silos, output parsers)
            agents = self.app_repo.get_agents_by_app_id(app_id)
            for agent in agents:
                logger.info(f"Deleting agent {agent.agent_id}: {agent.name}")
                agent_service.delete_agent(self.db, agent.agent_id)
            
            # 2. Delete resources (they depend on repositories)
            repositories = self.app_repo.get_repositories_by_app_id(app_id)
            for repository in repositories:
                resources = resource_service.get_resources_by_repo_id(repository.repository_id, self.db)
                for resource in resources:
                    logger.info(f"Deleting resource {resource.resource_id}: {resource.name}")
                    resource_service.delete_resource(resource.resource_id, self.db)
            
            # 3. Delete URLs (they depend on domains)
            domains = self.app_repo.get_domains_by_app_id(app_id)
            for domain in domains:
                urls = self.app_repo.get_urls_by_domain_id(domain.domain_id)
                for url in urls:
                    logger.info(f"Deleting URL {url.url_id}: {url.url}")
                    url_service.delete_url(url.url_id, domain.domain_id, self.db)
            
            # 4. Delete repositories (they depend on silos)
            for repository in repositories:
                logger.info(f"Deleting repository {repository.repository_id}: {repository.name}")
                repository_service.delete_repository(repository, self.db)
            
            # 5. Delete domains (they depend on silos)
            for domain in domains:
                logger.info(f"Deleting domain {domain.domain_id}: {domain.name}")
                domain_service.delete_domain(domain.domain_id, self.db)
            
            # 6. Delete silos (they depend on embedding services and output parsers)
            silos = self.app_repo.get_silos_by_app_id(app_id)
            for silo in silos:
                logger.info(f"Deleting silo {silo.silo_id}: {silo.name}")
                silo_service.delete_silo(silo.silo_id, self.db)
            
            # 7. Delete output parsers
            output_parsers = self.app_repo.get_output_parsers_by_app_id(app_id)
            for parser in output_parsers:
                logger.info(f"Deleting output parser {parser.parser_id}: {parser.name}")
                output_parser_service.delete_output_parser(self.db, app_id, parser.parser_id)
            
            # 8. Delete MCP configs
            mcp_configs = self.app_repo.get_mcp_configs_by_app_id(app_id)
            for config in mcp_configs:
                logger.info(f"Deleting MCP config {config.config_id}: {config.name}")
                mcp_config_service.delete_mcp_config(self.db, app_id, config.config_id)
            
            # 9. Delete API keys
            api_keys = self.app_repo.get_api_keys_by_app_id(app_id)
            for api_key in api_keys:
                logger.info(f"Deleting API key {api_key.key_id}: {api_key.name}")
                api_key_service.delete_api_key(self.db, app_id, api_key.key_id)
            
            # 10. Delete AI services
            ai_services = self.app_repo.get_ai_services_by_app_id(app_id)
            for service in ai_services:
                logger.info(f"Deleting AI service {service.service_id}: {service.name}")
                ai_service_service.delete_ai_service(self.db, app_id, service.service_id)
            
            # 11. Delete embedding services
            embedding_services = self.app_repo.get_embedding_services_by_app_id(app_id)
            for service in embedding_services:
                logger.info(f"Deleting embedding service {service.service_id}: {service.name}")
                embedding_service_service.delete_embedding_service(self.db, app_id, service.service_id)
            
            # 12. Delete collaborations
            collaborations = self.collaboration_repo.get_collaborations_by_app(app_id)
            for collab in collaborations:
                logger.info(f"Deleting collaboration {collab.id}")
                self.collaboration_repo.delete_collaboration(collab)
            
            # 13. Finally, delete the app
            success = self.app_repo.delete(app)
            
            if success:
                logger.info(f"Successfully deleted app {app_id} and all related data")
            
            return success
                
        except Exception as e:
            logger.error(f"Error during cascade deletion of app {app_id}: {str(e)}")
            # Rollback the transaction
            self.db.rollback()
            return False 