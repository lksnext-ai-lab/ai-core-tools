from typing import List, Optional, Tuple
from model.domain import Domain
from model.url import Url
from extensions import db
from services.silo_service import SiloService
from services.output_parser_service import OutputParserService
from model.silo import SiloType
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
            
        def query_operation():
            return db.session.query(Domain).filter(Domain.domain_id == domain_id).first()
        
        domain = safe_db_execute(query_operation, "get_domain")
        if domain:
            logger.debug(f"Retrieved domain {domain_id}: {domain.name}")
        return domain
    
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
            
        def query_operation():
            return db.session.query(Domain).filter(Domain.app_id == app_id).all()
        
        domains = safe_db_execute(query_operation, "get_domains_by_app_id")
        logger.info(f"Retrieved {len(domains)} domains for app {app_id}")
        return domains
    
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
        
        def query_operation():
            # Get total count
            total_urls = db.session.query(Url).filter(Url.domain_id == domain_id).count()
            
            # Get URLs for current page
            offset = (page - 1) * per_page
            urls = db.session.query(Url).filter(Url.domain_id == domain_id).offset(offset).limit(per_page).all()
            
            return urls, total_urls
        
        urls, total_count = safe_db_execute(query_operation, "get_domain_with_urls")
        
        pagination_info = {
            'page': page,
            'per_page': per_page,
            'total': total_count,
            'has_prev': page > 1,
            'has_next': (page * per_page) < total_count,
            'prev_num': page - 1 if page > 1 else None,
            'next_num': page + 1 if (page * per_page) < total_count else None
        }
        
        logger.debug(f"Retrieved {len(urls)} URLs for domain {domain_id} (page {page}/{per_page})")
        return domain, urls, pagination_info
    
    @staticmethod
    @handle_database_errors("create_or_update_domain") 
    def create_or_update_domain(domain_data: dict, embedding_service_id: Optional[int] = None) -> Domain:
        """
        Create a new domain or update an existing one
        
        Args:
            domain_data: Dictionary containing domain data
            embedding_service_id: Optional embedding service ID
            
        Returns:
            Created or updated Domain instance
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
        
        def create_or_update_operation():
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
                
                db.session.add(domain)
                db.session.flush()  # Get the ID
                
                # Now create domain filter with the domain object
                output_parser_service = OutputParserService()
                domain_filter = output_parser_service.create_default_filter_for_domain(domain)
                silo.metadata_definition_id = domain_filter.parser_id
                
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
                
                db.session.add(domain)
                db.session.flush()
            
            return domain
        
        domain = safe_db_execute(create_or_update_operation, "create_or_update_domain")
        logger.info(f"Successfully {'created' if not domain_id or domain_id == 0 else 'updated'} domain: {domain.name}")
        return domain
    
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
        
        def delete_operation():
            # Delete associated URLs
            deleted_urls = db.session.query(Url).filter(Url.domain_id == domain_id).delete()
            logger.debug(f"Deleted {deleted_urls} URLs for domain {domain_id}")
            
            # Delete the domain
            db.session.delete(domain)
            db.session.flush()
            
            return True
        
        result = safe_db_execute(delete_operation, "delete_domain")
        
        # Delete associated silo (outside the main transaction)
        if domain.silo_id:
            try:
                SiloService.delete_silo(domain.silo_id)
                logger.debug(f"Deleted silo {domain.silo_id} for domain {domain_id}")
            except Exception as e:
                logger.warning(f"Failed to delete silo {domain.silo_id} for domain {domain_id}: {e}")
        
        logger.info(f"Successfully deleted domain {domain_id}: {domain.name}")
        return result
    
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
    
    
    