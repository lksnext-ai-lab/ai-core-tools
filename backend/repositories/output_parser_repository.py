from typing import List, Optional
from sqlalchemy.orm import Session
from models.output_parser import OutputParser


class OutputParserRepository:
    """Repository for OutputParser data access operations"""
    
    def get_by_app_id(self, db: Session, app_id: int) -> List[OutputParser]:
        """Get all output parsers for a specific app"""
        return db.query(OutputParser).filter(OutputParser.app_id == app_id).all()
    
    def get_by_id(self, db: Session, parser_id: int) -> Optional[OutputParser]:
        """Get an output parser by its ID"""
        return db.query(OutputParser).filter(OutputParser.parser_id == parser_id).first()
    
    def get_by_id_and_app_id(self, db: Session, parser_id: int, app_id: int) -> Optional[OutputParser]:
        """Get an output parser by its ID and app ID"""
        return db.query(OutputParser).filter(
            OutputParser.parser_id == parser_id,
            OutputParser.app_id == app_id
        ).first()
    
    def get_available_parsers_for_app(self, db: Session, app_id: int, exclude_parser_id: Optional[int] = None) -> List[OutputParser]:
        """Get available parsers for references (excluding specified parser to prevent self-reference)"""
        query = db.query(OutputParser).filter(OutputParser.app_id == app_id)
        
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
            OutputParser.app_id == app_id
        ).first()
