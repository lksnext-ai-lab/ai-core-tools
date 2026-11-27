from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import exists
from models.output_parser import OutputParser
from models.repository import PLAYGROUND_MEDIA_REPO_TYPE, Repository
from models.silo import Silo


class OutputParserRepository:
    """Repository for OutputParser data access operations"""
    
    @staticmethod
    def visible_clause():
        """SQL clause: the parser is NOT the metadata parser of a hidden conversation temp silo.

        Every temp repository gets a ``DEFAULT-REPO-FILTER-_playground_<agent>_<session>`` parser that would reveal
        the session id of a conversation with indexed files. Lookups reachable by users, API keys and pickers add this
        clause; the silo's own ``metadata_definition`` relationship and the repository delete do not (they need it).
        """
        return ~exists().where(
            Silo.metadata_definition_id == OutputParser.parser_id,
            Repository.silo_id == Silo.silo_id,
            Repository.type == PLAYGROUND_MEDIA_REPO_TYPE,
        )

    def get_by_app_id(self, db: Session, app_id: int) -> List[OutputParser]:
        """Get the user-visible output parsers for a specific app"""
        return db.query(OutputParser).filter(OutputParser.app_id == app_id, self.visible_clause()).all()
    
    def get_by_id(self, db: Session, parser_id: int) -> Optional[OutputParser]:
        """Get an output parser by its ID"""
        return db.query(OutputParser).filter(OutputParser.parser_id == parser_id).first()
    
    def get_by_id_and_app_id(self, db: Session, parser_id: int, app_id: int) -> Optional[OutputParser]:
        """Get an output parser by its ID and app ID"""
        return db.query(OutputParser).filter(
            OutputParser.parser_id == parser_id,
            OutputParser.app_id == app_id,
            self.visible_clause(),
        ).first()
    
    def get_available_parsers_for_app(self, db: Session, app_id: int, exclude_parser_id: Optional[int] = None) -> List[OutputParser]:
        """Get available parsers for references (excluding specified parser to prevent self-reference)"""
        query = db.query(OutputParser).filter(OutputParser.app_id == app_id, self.visible_clause())
        
        if exclude_parser_id is not None:
            query = query.filter(OutputParser.parser_id != exclude_parser_id)
            
        return query.all()
    
    def create(self, db: Session, parser: OutputParser) -> OutputParser:
        """Create a new output parser"""
        db.add(parser)
        db.commit()
        db.refresh(parser)
        return parser
    
    def update(self, db: Session, parser: OutputParser) -> OutputParser:
        """Update an existing output parser"""
        db.add(parser)
        db.commit()
        db.refresh(parser)
        return parser
    
    def delete(self, db: Session, parser: OutputParser) -> bool:
        """Delete an output parser"""
        try:
            db.delete(parser)
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False
    
    def delete_by_id(self, db: Session, parser_id: int) -> bool:
        """Delete an output parser by its ID"""
        try:
            db.query(OutputParser).filter(OutputParser.parser_id == parser_id).delete()
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False

    def get_by_name_and_app_id(
        self, db: Session, name: str, app_id: int
    ) -> Optional[OutputParser]:
        """Get an output parser by its name and app ID"""
        return db.query(OutputParser).filter(
            OutputParser.name == name,
            OutputParser.app_id == app_id,
            self.visible_clause(),
        ).first()
