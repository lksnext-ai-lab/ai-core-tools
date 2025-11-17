from typing import List, Optional, Tuple
from models.domain import Domain
from models.url import Url
from models.silo import SiloType
from schemas.domain_url_schemas import DomainDetailSchema
from sqlalchemy.orm import Session
from repositories.domain_repository import DomainRepository
from repositories.embedding_service_repository import EmbeddingServiceRepository
from repositories.silo_repository import SiloRepository
from services.silo_service import SiloService
from services.output_parser_service import OutputParserService
from utils.logger import get_logger
from utils.error_handlers import (
    handle_database_errors, NotFoundError, ValidationError, 
    validate_required_fields
)
from tools.vector_store_factory import VectorStoreFactory
import config
logger = get_logger(__name__)


class DomainService:

    @staticmethod
    @handle_database_errors("get_domain")
    def get_domain(domain_id: int, db: Session) -> Optional[Domain]:
        """
        Get a domain by ID
        
        Args:
            domain_id: ID of the domain
            db: Database session
            
        Returns:
            Domain instance or None if not found
        """
        if not domain_id or domain_id <= 0:
            return None
        
        domain = DomainRepository.get_by_id(domain_id, db)
        if domain:
            logger.debug(f"Retrieved domain {domain_id}: {domain.name}")
        return domain
    
    @staticmethod
    @handle_database_errors("get_domains_by_app_id")
    def get_domains_by_app_id(app_id: int, db: Session) -> List[Domain]:
        """
        Get all domains for a specific app
        
        Args:
            app_id: ID of the app
            db: Database session
            
        Returns:
            List of domains
        """
        if not app_id:
            raise ValidationError("App ID is required")
        
        domains = DomainRepository.get_by_app_id(app_id, db)
        logger.info(f"Retrieved {len(domains)} domains for app {app_id}")
        return domains
    
    @staticmethod
    @handle_database_errors("get_domains_with_url_counts")
    def get_domains_with_url_counts(app_id: int, db: Session) -> List[Tuple[Domain, int]]:
        """
        Get all domains for a specific app with their URL counts
        
        Args:
            app_id: ID of the app
            db: Database session
            
        Returns:
            List of tuples (domain, url_count)
        """
        if not app_id:
            raise ValidationError("App ID is required")
        
        try:
            result = DomainRepository.get_domains_with_url_counts(app_id, db)
            logger.info(f"Retrieved {len(result)} domains with URL counts for app {app_id}")
            return result
        except Exception as e:
            logger.error(f"Error getting domains with URL counts for app {app_id}: {str(e)}")
            raise
    
    @staticmethod
    @handle_database_errors("get_embedding_services_for_app")
    def get_embedding_services_for_app(app_id: int, db: Session) -> List[dict]:
        """
        Get embedding services for a specific app
        
        Args:
            app_id: ID of the app
            db: Database session
            
        Returns:
            List of embedding service dictionaries
        """
        try:
            embedding_services_query = EmbeddingServiceRepository.get_by_app_id(db, app_id)
            embedding_services = [{"service_id": s.service_id, "name": s.name} for s in embedding_services_query]
            
            logger.debug(f"Retrieved {len(embedding_services)} embedding services for app {app_id}")
            return embedding_services
        except Exception as e:
            logger.error(f"Error getting embedding services for app {app_id}: {str(e)}")
            raise
    
    @staticmethod
    @handle_database_errors("get_domain_detail")
    def get_domain_detail(domain_id: int, app_id: int, db: Session) -> Optional[DomainDetailSchema]:
        """
        Get detailed information about a domain including URL count and embedding services
        
        Args:
            domain_id: ID of the domain
            app_id: ID of the app (for embedding services)
            db: Database session
            
        Returns:
            DomainDetailSchema or None if domain not found
        """
        try:
            domain_data = DomainRepository.get_domain_detail_data(domain_id, db)
            if not domain_data:
                return None
            
            domain, url_count, embedding_service_id = domain_data
            
            # Get embedding services for form data
            embedding_services = DomainService.get_embedding_services_for_app(app_id, db)
            vector_db_options = VectorStoreFactory.get_available_type_options()
            if domain.silo and getattr(domain.silo, 'vector_db_type', None):
                vector_db_type = domain.silo.vector_db_type
            else:
                default_type = config.VECTOR_DB_TYPE or 'PGVECTOR'
                vector_db_type = default_type.upper() if isinstance(default_type, str) else default_type
            
            return DomainDetailSchema(
                domain_id=domain.domain_id,
                name=domain.name,
                description=domain.description or "",
                base_url=domain.base_url,
                content_tag=domain.content_tag or "body",
                content_class=domain.content_class or "",
                content_id=domain.content_id or "",
                created_at=domain.create_date,
                silo_id=domain.silo_id,
                url_count=url_count,
                embedding_services=embedding_services,
                embedding_service_id=embedding_service_id,
                vector_db_type=vector_db_type,
                vector_db_options=vector_db_options
            )
            
        except Exception as e:
            logger.error(f"Error getting domain detail for domain {domain_id}: {str(e)}")
            raise
    
    @staticmethod
    @handle_database_errors("get_domain_with_urls")
    def get_domain_with_urls(domain_id: int, db: Session, page: int = 1, per_page: int = 20) -> Tuple[Optional[Domain], List[Url], dict]:
        """
        Get a domain with its URLs with pagination
        
        Args:
            domain_id: ID of the domain
            db: Database session
            page: Page number (1-based)
            per_page: Number of items per page
            
        Returns:
            Tuple of (domain, urls_for_page, pagination_info)
        """
        domain, urls, pagination_info = DomainRepository.get_domain_with_urls_paginated(domain_id, db, page, per_page)
        
        if not domain:
            raise NotFoundError(f"Domain with ID {domain_id} not found", "domain")
        
        logger.debug(f"Retrieved {len(urls)} URLs for domain {domain_id} (page {page}/{per_page})")
        return domain, urls, pagination_info
    
    @staticmethod
    @handle_database_errors("create_or_update_domain") 
    def create_or_update_domain(domain_data: dict, embedding_service_id: Optional[int] = None, db: Session = None) -> int:
        """
        Create a new domain or update an existing one
        
        Args:
            domain_data: Dictionary containing domain data
            embedding_service_id: Optional embedding service ID
            db: Database session (required)
            
        Returns:
            domain_id of the created or updated domain
        """
        if db is None:
            raise ValidationError("Database session is required")
            
        # Validate required fields
        required_fields = ['name', 'base_url', 'app_id']
        validate_required_fields(domain_data, required_fields)
        
        # Clean and validate data
        name = domain_data['name'].strip()
        base_url = domain_data['base_url'].strip()
        
        if not name:
            raise ValidationError("Domain name cannot be empty")
        if not base_url:
            raise ValidationError("Base URL cannot be empty")
        
        raw_vector_db_type = domain_data.get('vector_db_type')
        if raw_vector_db_type is not None:
            if not isinstance(raw_vector_db_type, str):
                raise ValidationError("vector_db_type must be a string")
            raw_vector_db_type = raw_vector_db_type.strip().upper()
            if not raw_vector_db_type:
                raw_vector_db_type = None
            elif raw_vector_db_type not in VectorStoreFactory.IMPLEMENTED_TYPES:
                raise ValidationError(
                    f"Unsupported vector_db_type '{raw_vector_db_type}'."
                )

        domain_id = domain_data.get('domain_id')
        
        if not domain_id or domain_id == 0 or domain_id == '0':
            # Create new domain
            return DomainService._create_new_domain(domain_data, embedding_service_id, name, base_url, raw_vector_db_type, db)
        else:
            # Update existing domain
            return DomainService._update_existing_domain(domain_id, domain_data, embedding_service_id, name, base_url, raw_vector_db_type, db)
    
    @staticmethod
    def _create_new_domain(domain_data: dict, embedding_service_id: Optional[int], name: str, base_url: str, vector_db_type: Optional[str], db: Session = None) -> int:
        """Create a new domain with associated silo"""
        logger.info(f"Creating new domain: {name}")

        resolved_vector_db_type = (vector_db_type or config.VECTOR_DB_TYPE).upper()
        
        # Create associated silo
        silo_data = {
            'silo_id': 0,
            'name': f'silo for domain {name}',
            'description': f'silo for domain {name}',
            'status': 'active',
            'app_id': domain_data['app_id'],
            'fixed_metadata': False,
            'embedding_service_id': embedding_service_id,
            'vector_db_type': resolved_vector_db_type
        }
        silo = SiloService.create_or_update_silo(silo_data, SiloType.DOMAIN)
        
        # Create domain
        domain = Domain(
            name=name,
            description=domain_data.get('description', '').strip() or None,
            base_url=base_url,
            content_tag=domain_data.get('content_tag', '').strip() or None,
            content_class=domain_data.get('content_class', '').strip() or None,
            content_id=domain_data.get('content_id', '').strip() or None,
            app_id=domain_data['app_id'],
            silo_id=silo.silo_id
        )
        
        created_domain = DomainRepository.create(domain, db)
        
        # Create domain filter
        output_parser_service = OutputParserService()
        domain_filter_id = output_parser_service.create_default_filter_for_domain(
            db=db,
            silo_id=silo.silo_id,
            domain_name=name,
            app_id=domain_data['app_id']
        )
        
        # Update silo with metadata_definition_id
        silo.metadata_definition_id = domain_filter_id
        SiloRepository.update(silo, db)
        
        return created_domain.domain_id
    
    @staticmethod
    def _update_existing_domain(domain_id: int, domain_data: dict, embedding_service_id: Optional[int], name: str, base_url: str, vector_db_type: Optional[str], db: Session) -> int:
        """Update an existing domain and its associated silo"""
        logger.info(f"Updating domain {domain_id}")
        domain = DomainService.get_domain(domain_id, db)
        if not domain:
            raise NotFoundError(f"Domain with ID {domain_id} not found", "domain")
        
        # Update domain fields
        domain.name = name
        domain.description = domain_data.get('description', '').strip() or None
        domain.base_url = base_url
        domain.content_tag = domain_data.get('content_tag', '').strip() or None
        domain.content_class = domain_data.get('content_class', '').strip() or None
        domain.content_id = domain_data.get('content_id', '').strip() or None
        
        updated_domain = DomainRepository.update(domain, db)
        
        # Update the associated silo's embedding service if provided
        if domain.silo_id and embedding_service_id is not None:
            logger.info(f"Updating embedding service for silo {domain.silo_id} to service {embedding_service_id}")
            silo = SiloService.get_silo(domain.silo_id, db)
            if silo:
                silo.embedding_service_id = embedding_service_id
                if vector_db_type:
                    silo.vector_db_type = vector_db_type
                elif not silo.vector_db_type:
                    default_type = config.VECTOR_DB_TYPE or 'PGVECTOR'
                    silo.vector_db_type = default_type.upper() if isinstance(default_type, str) else default_type
                SiloRepository.update(silo, db)
                logger.info(f"Successfully updated silo {domain.silo_id} embedding service")
            else:
                logger.warning(f"Silo {domain.silo_id} not found for domain {domain_id}")

        if domain.silo_id and vector_db_type and embedding_service_id is None:
            silo = SiloService.get_silo(domain.silo_id, db)
            if silo:
                silo.vector_db_type = vector_db_type
                SiloRepository.update(silo, db)
        elif domain.silo_id and not vector_db_type:
            silo = SiloService.get_silo(domain.silo_id, db)
            if silo and not silo.vector_db_type:
                default_type = config.VECTOR_DB_TYPE or 'PGVECTOR'
                silo.vector_db_type = default_type.upper() if isinstance(default_type, str) else default_type
                SiloRepository.update(silo, db)
        
        return updated_domain.domain_id
    
    @staticmethod
    @handle_database_errors("delete_domain")
    def delete_domain(domain_id: int, db: Session) -> bool:
        """
        Delete a domain and all associated data
        
        Args:
            domain_id: ID of the domain to delete
            db: Database session
            
        Returns:
            True if deleted successfully
        """
        domain = DomainService.get_domain(domain_id, db)
        if not domain:
            raise NotFoundError(f"Domain with ID {domain_id} not found", "domain")
        
        # Store domain info before deletion operations
        domain_name = domain.name
        silo_id = domain.silo_id
        
        # Delete domain and associated URLs using repository
        DomainRepository.delete_with_urls(domain_id, db)
        
        logger.info(f"Successfully deleted domain {domain_id}: {domain_name}")
        
        # Delete associated silo and all its data structures (silo, collection, output parser)
        if silo_id:
            try:
                SiloService.delete_silo(silo_id, db)
                logger.debug(f"Deleted silo {silo_id} and associated data structures for domain {domain_id}")
            except Exception as e:
                logger.warning(f"Failed to delete silo {silo_id} for domain {domain_id}: {e}")
                # Don't fail the whole operation if silo deletion fails
        
        return True
    
    @staticmethod
    def validate_domain_data(form_data: dict) -> dict:
        """
        Validate and clean domain form data
        
        Args:
            form_data: Raw form data dictionary
            
        Returns:
            Cleaned and validated data dictionary
        """
        cleaned_data = {
            "name": form_data.get('name', '').strip(),
            "description": form_data.get('description', '').strip(),
            "base_url": form_data.get('base_url', '').strip(),
            "content_tag": form_data.get('content_tag', '').strip(),
            "content_class": form_data.get('content_class', '').strip(),
            "content_id": form_data.get('content_id', '').strip(),
            "app_id": form_data.get('app_id'),
            "silo_id": form_data.get('silo_id')
        }
        
        # Convert string IDs to integers
        for field in ['app_id', 'silo_id', 'domain_id']:
            if field in form_data and form_data[field]:
                try:
                    cleaned_data[field] = int(form_data[field])
                except (ValueError, TypeError):
                    if field == 'app_id':  # app_id is required
                        raise ValidationError(f"Invalid {field}: {form_data[field]}")
        
        return cleaned_data 