from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from models.output_parser import OutputParser
from models.repository import Repository
from repositories.output_parser_repository import OutputParserRepository
from schemas.output_parser_schemas import (
    OutputParserListItemSchema,
    OutputParserDetailSchema,
    OutputParserFieldSchema,
    CreateUpdateOutputParserSchema
)
from datetime import datetime

class OutputParserService:
    def __init__(self):
        self.field_types = ['str', 'int', 'float', 'bool', 'date', 'list']
        self.repository = OutputParserRepository()
    
    def list_output_parsers(self, db: Session, app_id: int) -> List[OutputParserListItemSchema]:
        """
        List all output parsers (data structures) for a specific app.
        """
        parsers = self.repository.get_by_app_id(db, app_id)
        
        result = []
        for parser in parsers:
            field_count = len(parser.fields) if parser.fields else 0
            result.append(OutputParserListItemSchema(
                parser_id=parser.parser_id,
                name=parser.name,
                description=parser.description,
                field_count=field_count,
                created_at=parser.create_date
            ))
        
        return result
    
    def get_output_parser_detail(self, db: Session, app_id: int, parser_id: int) -> OutputParserDetailSchema:
        """
        Get detailed information about a specific output parser including its fields.
        """
        # Get available parsers for references (excluding current parser to prevent self-reference)
        exclude_parser_id = parser_id if parser_id != 0 else None
        available_parsers_list = self.repository.get_available_parsers_for_app(db, app_id, exclude_parser_id)
        
        available_parsers = [
            {"value": p.parser_id, "name": p.name}
            for p in available_parsers_list
        ]
        
        if parser_id == 0:
            # New output parser
            return OutputParserDetailSchema(
                parser_id=0,
                name="",
                description="",
                fields=[],
                created_at=None,
                available_parsers=available_parsers
            )
        
        # Existing output parser
        parser = self.repository.get_by_id_and_app_id(db, parser_id, app_id)
        
        if not parser:
            return None
        
        # Convert JSON fields to schema format
        fields = []
        if parser.fields:
            for field_data in parser.fields:
                fields.append(OutputParserFieldSchema(
                    name=field_data.get('name', ''),
                    type=field_data.get('type', 'str'),
                    description=field_data.get('description', ''),
                    parser_id=field_data.get('parser_id'),
                    list_item_type=field_data.get('list_item_type'),
                    list_item_parser_id=field_data.get('list_item_parser_id')
                ))
        
        return OutputParserDetailSchema(
            parser_id=parser.parser_id,
            name=parser.name,
            description=parser.description,
            fields=fields,
            created_at=parser.create_date,
            available_parsers=available_parsers
        )
    
    def create_or_update_output_parser(self, db: Session, app_id: int, parser_id: int, 
                                     parser_data: CreateUpdateOutputParserSchema) -> OutputParser:
        """
        Create a new output parser or update an existing one.
        """
        if parser_id == 0:
            # Create new output parser
            parser = OutputParser()
            parser.app_id = app_id
            parser.create_date = datetime.now()
        else:
            # Update existing output parser
            parser = self.repository.get_by_id_and_app_id(db, parser_id, app_id)
            
            if not parser:
                return None
        
        # Update parser data
        parser.name = parser_data.name
        parser.description = parser_data.description
        
        # Convert fields to JSON format
        fields_json = []
        for field_data in parser_data.fields:
            if not field_data.name:  # Skip empty field names
                continue
                
            field_dict = {
                'name': field_data.name,
                'type': field_data.type,
                'description': field_data.description
            }
            
            if field_data.type == 'parser' and field_data.parser_id:
                field_dict['parser_id'] = field_data.parser_id
            elif field_data.type == 'list':
                if field_data.list_item_type:
                    field_dict['list_item_type'] = field_data.list_item_type
                if field_data.list_item_type == 'parser' and field_data.list_item_parser_id:
                    field_dict['list_item_parser_id'] = field_data.list_item_parser_id
            
            fields_json.append(field_dict)
        
        parser.fields = fields_json
        
        if parser_id == 0:
            return self.repository.create(db, parser)
        else:
            return self.repository.update(db, parser)
    
    def delete_output_parser(self, db: Session, app_id: int, parser_id: int) -> bool:
        """
        Delete an output parser.
        """
        parser = self.repository.get_by_id_and_app_id(db, parser_id, app_id)
        
        if not parser:
            return False
        
        return self.repository.delete(db, parser)
    
    def get_parsers_by_app(self, db: Session, app_id: int) -> List[OutputParser]:
        """Obtiene todos los parsers de una aplicación"""
        return self.repository.get_by_app_id(db, app_id)
    
    def get_parser_by_id(self, db: Session, parser_id: int) -> Optional[OutputParser]:
        """Obtiene un parser específico por su ID"""
        return self.repository.get_by_id(db, parser_id)
    
    def create_or_update_parser(self, db: Session, parser_id: int, data: Dict) -> OutputParser:
        """Crea o actualiza un parser con los datos proporcionados"""
        parser = self.get_parser_by_id(db, parser_id) or OutputParser()
        
        parser.name = data['name']
        parser.description = data.get('description')
        parser.app_id = data['app_id']
        parser.fields = self._process_fields(
            data.get('field_names', []),
            data.get('field_types', []),
            data.get('field_descriptions', []),
            data.get('list_item_types', [])
        )
        
        if parser_id == 0:
            return self.repository.create(db, parser)
        else:
            return self.repository.update(db, parser)
    
    def delete_parser(self, db: Session, parser_id: int) -> bool:
        """Elimina un parser por su ID"""
        return self.repository.delete_by_id(db, parser_id)
    
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
    
    def create_default_filter_for_repo(self, db: Session, repository: Repository) -> int:
        parser = OutputParser()
        parser.name = f"DEFAULT-REPO-FILTER-{repository.name}"
        parser.description = f"Default filter for repository ({repository.name})"
        parser.app_id = repository.app_id
        parser.fields = [{"name": "name", "description": "Name of the file", "type": "str"}, {"name": "page", "description": "page of the document or chunk", "type": "int"}, {"name": "ref", "description": "reference of the file", "type": "str"}, {"name": "resource_id", "description": "resource id", "type": "int"}, {"name": "repository_id", "description": "repo id", "type": "int"}, {"name": "silo_id", "description": "silo id", "type": "int"}]
        created_parser = self.repository.create(db, parser)
        return created_parser.parser_id
    
    def create_default_filter_for_domain(self, db: Session, silo_id: int, domain_name: str, app_id: int) -> int:
        parser = OutputParser()
        parser.name = f"DEFAULT-DOMAIN-FILTER-{silo_id}"
        parser.description = f"Default filter for domain ({domain_name})"
        parser.app_id = app_id
        parser.fields = [{"name":"url_id","description":"url id","type":"int"}, {"name":"url","description":"url","type":"str"}, {"name":"domain_id","description":"domain id","type":"int"}, {"name":"page","description":"page of the document or chunk","type":"int"}]
        created_parser = self.repository.create(db, parser)
        return created_parser.parser_id 