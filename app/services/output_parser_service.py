from typing import List, Dict, Optional
from app.extensions import db
from app.model.output_parser import OutputParser
from app.model.repository import Repository
from app.model.domain import Domain
class OutputParserService:
    def __init__(self):
        self.field_types = ['str', 'int', 'float', 'bool', 'list']
    
    def get_parsers_by_app(self, app_id: int) -> List[OutputParser]:
        """Obtiene todos los parsers de una aplicación"""
        return db.session.query(OutputParser).filter(OutputParser.app_id == app_id).all()
    
    def get_parser_by_id(self, parser_id: int) -> Optional[OutputParser]:
        """Obtiene un parser específico por su ID"""
        return db.session.query(OutputParser).filter(OutputParser.parser_id == parser_id).first()
    
    def create_or_update_parser(self, parser_id: int, data: Dict) -> OutputParser:
        """Crea o actualiza un parser con los datos proporcionados"""
        parser = self.get_parser_by_id(parser_id) or OutputParser()
        
        parser.name = data['name']
        parser.description = data.get('description')
        parser.app_id = data['app_id']
        parser.fields = self._process_fields(
            data.get('field_names', []),
            data.get('field_types', []),
            data.get('field_descriptions', []),
            data.get('list_item_types', [])
        )
        
        db.session.add(parser)
        db.session.commit()
        return parser
    
    def delete_parser(self, parser_id: int) -> bool:
        """Elimina un parser por su ID"""
        try:
            db.session.query(OutputParser).filter(OutputParser.parser_id == parser_id).delete()
            db.session.commit()
            return True
        except Exception:
            db.session.rollback()
            return False
    
    def _process_fields(self, names: List[str], types: List[str], 
                       descriptions: List[str], list_types: List[str]) -> List[Dict]:
        """Procesa y valida los campos del parser"""
        fields = []
        
        for i, (name, type_, description) in enumerate(zip(names, types, descriptions)):
            if not name:
                continue
                
            field = {
                'name': name,
                'description': description
            }
            
            if type_.startswith('parser:'):
                field['type'] = 'parser'
                field['parser_id'] = int(type_.split(':')[1])
            else:
                field['type'] = type_
            
            if type_ == 'list':
                list_type = list_types[i]
                if list_type.startswith('parser:'):
                    field['list_item_type'] = 'parser'
                    field['list_item_parser_id'] = int(list_type.split(':')[1])
                else:
                    field['list_item_type'] = list_type
            
            fields.append(field)
            
        return fields 
    
    def create_default_filter_for_repo(self, repository: Repository) -> OutputParser:
        parser = OutputParser()
        parser.name = f"DEFAULT-REPO-FILTER-{repository.silo_id}"
        parser.description = "Default filter for repository"
        parser.app_id = repository.app_id
        parser.fields = [{"name": "name", "description": "Name of the file", "type": "str"}, {"name": "page", "description": "page of the document or chunk", "type": "int"}, {"name": "ref", "description": "reference of the file", "type": "str"}, {"name": "resource_id", "description": "resource id", "type": "int"}, {"name": "repository_id", "description": "repo id", "type": "int"}, {"name": "silo_id", "description": "silo id", "type": "int"}]
        db.session.add(parser)
        db.session.commit()
        return parser
    
    def create_default_filter_for_domain(self, domain: Domain) -> OutputParser:
        parser = OutputParser()
        parser.name = f"DEFAULT-DOMAIN-FILTER-{domain.silo_id}"
        parser.description = "Default filter for domain"
        parser.app_id = domain.app_id
        parser.fields = [{"name":"url_id","description":"url id","type":"int"}, {"name":"url","description":"url","type":"str"}, {"name":"domain_id","description":"domain id","type":"int"}, {"name":"page","description":"page of the document or chunk","type":"int"}]
        db.session.add(parser)
        db.session.commit()
        return parser