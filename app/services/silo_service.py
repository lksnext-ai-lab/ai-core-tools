from typing import Optional, List
from app.model.silo import Silo
from app.model.output_parser import OutputParser
from app.extensions import db

class SiloService:
    @staticmethod
    def get_silo(silo_id: int) -> Optional[Silo]:
        """
        Retrieve a silo by its ID
        """
        return db.session.query(Silo).filter(Silo.silo_id == silo_id).first()
    
    @staticmethod
    def get_silos_by_app_id(app_id: int) -> List[Silo]:
        """
        Retrieve all silos by app_id
        """
        return db.session.query(Silo).filter(Silo.app_id == app_id).all()
    
    @staticmethod
    def create_or_update_silo(silo_data: dict) -> Silo:
        """
        Create a new silo or update an existing one
        """
        silo_id = int(silo_data.get('silo_id'))
        silo = SiloService.get_silo(silo_id) if silo_id else None
        
        if not silo:
            silo = Silo()
            
        SiloService._update_silo(silo, silo_data)
        db.session.add(silo)
        db.session.commit()
        return silo
    
    @staticmethod
    def _update_silo(silo: Silo, data: dict):
        """
        Update silo attributes from input data
        """
        silo.name = data['name']
        silo.description = data.get('description')
        silo.status = data.get('status')
        silo.app_id = data['app_id']
        silo.fixed_metadata = data.get('fixed_metadata', False)
        silo.metadata_definition_id = data.get('metadata_definition_id') or None
    
    @staticmethod
    def get_silo_form_data(app_id: int, silo_id: int) -> dict:
        """
        Get data needed for rendering the silo form
        
        Args:
            app_id: ID of the application
            silo_id: ID of the silo to edit (0 for new silo)
            
        Returns:
            Dictionary with form data
        """
        output_parsers = db.session.query(OutputParser).filter(OutputParser.app_id == app_id).all()
        
        if silo_id == 0:
            return {
                'app_id': app_id,
                'silo': Silo(silo_id=0, name=""),
                'output_parsers': output_parsers
            }
        
        silo = db.session.query(Silo).filter(Silo.silo_id == silo_id).first()
        return {
            'app_id': app_id,
            'silo': silo,
            'output_parsers': output_parsers
        }
    
    @staticmethod
    def delete_silo(silo_id: int):
        """
        Delete a silo by its ID
        """
        silo = db.session.query(Silo).filter(Silo.silo_id == silo_id).first()
        if silo:
            db.session.delete(silo)
            db.session.commit()
