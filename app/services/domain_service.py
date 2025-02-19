from app.model.domain import Domain
from app.extensions import db
from app.services.silo_service import SiloService
from app.services.output_parser_service import OutputParserService
from app.model.silo import SiloType
from app.model.url import Url
class DomainService:

    @staticmethod
    def get_domain(domain_id: int) -> Domain:
        return db.session.query(Domain).filter(Domain.domain_id == domain_id).first()
    
    @staticmethod
    def create_or_update_domain(domain: Domain) -> Domain:
        if domain.domain_id is None or domain.domain_id == '0':
            silo_service = SiloService()
            silo_data = {
                'silo_id': 0,
                'name': 'silo for repository ' + domain.name,
                'description': 'silo for repository ' + domain.name,
                'status': 'active',
                'app_id': domain.app_id,
                'fixed_metadata': False
            }
            silo = silo_service.create_or_update_silo(silo_data, SiloType.DOMAIN)
            domain.silo_id = silo.silo_id
            output_parser_service = OutputParserService()
            filter = output_parser_service.create_default_filter_for_domain(domain)
            silo.metadata_definition_id = filter.parser_id
            
            # For new domains, set id to None and add
            domain.domain_id = None
            
            db.session.add(domain)
        else:
            # For existing domains, use merge
            db.session.merge(domain)
        
        db.session.commit()
        return domain
    
    @staticmethod
    def delete_domain(domain: Domain):
        db.session.query(Url).filter(Url.domain_id == domain.domain_id).delete()
        db.session.delete(domain)
        silo_service = SiloService()
        silo_service.delete_silo(domain.silo_id)
        db.session.commit()
    
    
    