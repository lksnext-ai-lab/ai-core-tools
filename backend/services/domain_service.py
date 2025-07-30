from typing import List, Optional, Tuple
from models.domain import Domain
from models.url import Url
from db.session import SessionLocal
from services.silo_service import SiloService
from services.output_parser_service import OutputParserService
from models.silo import SiloType, Silo
from utils.logger import get_logger
from utils.error_handlers import (
    handle_database_errors, NotFoundError, ValidationError, 
    validate_required_fields, safe_execute
)
from utils.database import safe_db_execute

logger = get_logger(__name__)


class DomainService:

    @staticmethod
    @handle_database_errors("get_domain")
    def get_domain(domain_id: int) -> Optional[Domain]:
        """
        Get a domain by ID
        
        Args:
            domain_id: ID of the domain
            
        Returns:
            Domain instance or None if not found
        """
        if not domain_id or domain_id <= 0:
            return None
        
        session = SessionLocal()
        try:
            domain = session.query(Domain).filter(Domain.domain_id == domain_id).first()
            if domain:
                logger.debug(f"Retrieved domain {domain_id}: {domain.name}")
            return domain
        finally:
            session.close()
    
    @staticmethod
    @handle_database_errors("get_domains_by_app_id")
    def get_domains_by_app_id(app_id: int) -> List[Domain]:
        """
        Get all domains for a specific app
        
        Args:
            app_id: ID of the app
            
        Returns:
            List of domains
        """
        if not app_id:
            raise ValidationError("App ID is required")
        
        session = SessionLocal()
        try:
            domains = session.query(Domain).filter(Domain.app_id == app_id).all()
            logger.info(f"Retrieved {len(domains)} domains for app {app_id}")
            return domains
        finally:
            session.close()
    
    @staticmethod
    @handle_database_errors("get_domain_with_urls")
    def get_domain_with_urls(domain_id: int, page: int = 1, per_page: int = 20) -> Tuple[Optional[Domain], List[Url], dict]:
        """
        Get a domain with its URLs with pagination
        
        Args:
            domain_id: ID of the domain
            page: Page number (1-based)
            per_page: Number of items per page
            
        Returns:
            Tuple of (domain, urls_for_page, pagination_info)
        """
        domain = DomainService.get_domain(domain_id)
        if not domain:
            raise NotFoundError(f"Domain with ID {domain_id} not found", "domain")
        
        session = SessionLocal()
        try:
            # Get total count
            total_urls = session.query(Url).filter(Url.domain_id == domain_id).count()
            
            # Get URLs for current page
            offset = (page - 1) * per_page
            urls = session.query(Url).filter(Url.domain_id == domain_id).offset(offset).limit(per_page).all()
            
            pagination_info = {
                'page': page,
                'per_page': per_page,
                'total': total_urls,
                'has_prev': page > 1,
                'has_next': (page * per_page) < total_urls,
                'prev_num': page - 1 if page > 1 else None,
                'next_num': page + 1 if (page * per_page) < total_urls else None
            }
            
            logger.debug(f"Retrieved {len(urls)} URLs for domain {domain_id} (page {page}/{per_page})")
            return domain, urls, pagination_info
        finally:
            session.close()
    
    @staticmethod
    @handle_database_errors("create_or_update_domain") 
    def create_or_update_domain(domain_data: dict, embedding_service_id: Optional[int] = None) -> int:
        """
        Create a new domain or update an existing one
        
        Args:
            domain_data: Dictionary containing domain data
            embedding_service_id: Optional embedding service ID
            
        Returns:
            domain_id of the created or updated domain
        """
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
        
        domain_id = domain_data.get('domain_id')
        
        session = SessionLocal()
        try:
            if not domain_id or domain_id == 0 or domain_id == '0':
                # Create new domain
                logger.info(f"Creating new domain: {name}")
                
                # Create associated silo
                silo_data = {
                    'silo_id': 0,
                    'name': f'silo for domain {name}',
                    'description': f'silo for domain {name}',
                    'status': 'active',
                    'app_id': domain_data['app_id'],
                    'fixed_metadata': False,
                    'embedding_service_id': embedding_service_id
                }
                silo = SiloService.create_or_update_silo(silo_data, SiloType.DOMAIN)
                
                # Create domain first
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
                
                session.add(domain)
                session.flush()  # Get the ID
                
                # Now create domain filter with domain data (avoid detached instance)
                output_parser_service = OutputParserService()
                domain_filter_id = output_parser_service.create_default_filter_for_domain(
                    silo_id=silo.silo_id,
                    domain_name=name,
                    app_id=domain_data['app_id']
                )
                
                # Update silo with metadata_definition_id in current session (avoid detached instance)
                silo_in_session = session.query(Silo).filter(Silo.silo_id == silo.silo_id).first()
                if silo_in_session:
                    silo_in_session.metadata_definition_id = domain_filter_id
                    session.add(silo_in_session)
                
            else:
                # Update existing domain
                logger.info(f"Updating domain {domain_id}")
                domain = DomainService.get_domain(domain_id)
                if not domain:
                    raise NotFoundError(f"Domain with ID {domain_id} not found", "domain")
                
                # Update fields
                domain.name = name
                domain.description = domain_data.get('description', '').strip() or None
                domain.base_url = base_url
                domain.content_tag = domain_data.get('content_tag', '').strip() or None
                domain.content_class = domain_data.get('content_class', '').strip() or None
                domain.content_id = domain_data.get('content_id', '').strip() or None
                
                session.add(domain)
                session.flush()
            
            session.commit()
            session.refresh(domain)  # Ensure we have the domain_id
            domain_id = domain.domain_id
            return domain_id
        finally:
            session.close()
    
    @staticmethod
    @handle_database_errors("delete_domain")
    def delete_domain(domain_id: int) -> bool:
        """
        Delete a domain and all associated data
        
        Args:
            domain_id: ID of the domain to delete
            
        Returns:
            True if deleted successfully
        """
        domain = DomainService.get_domain(domain_id)
        if not domain:
            raise NotFoundError(f"Domain with ID {domain_id} not found", "domain")
        
        # Store domain info before session operations (avoid DetachedInstanceError)
        domain_name = domain.name
        silo_id = domain.silo_id
        
        session = SessionLocal()
        try:
            # Delete associated URLs first
            deleted_urls = session.query(Url).filter(Url.domain_id == domain_id).delete()
            logger.debug(f"Deleted {deleted_urls} URLs for domain {domain_id}")
            
            # Delete the domain itself
            session.delete(domain)
            session.commit()
            
            logger.info(f"Successfully deleted domain {domain_id}: {domain_name}")
            
        finally:
            session.close()
        
        # Delete associated silo and all its data structures (silo, collection, output parser)
        if silo_id:
            try:
                SiloService.delete_silo(silo_id)
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