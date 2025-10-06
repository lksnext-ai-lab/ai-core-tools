from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime


class OutputParserListItemSchema(BaseModel):
    """Schema for output parser list items"""
    parser_id: int
    name: str
    description: Optional[str]
    field_count: int  # Number of fields in the parser
    created_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)


class OutputParserFieldSchema(BaseModel):
    """Schema for individual parser fields"""
    name: str
    type: str  # 'str', 'int', 'float', 'bool', 'date', 'list', 'parser'
    description: str
    parser_id: Optional[int] = None  # For type='parser'
    list_item_type: Optional[str] = None  # For type='list'
    list_item_parser_id: Optional[int] = None  # For list of parsers


class OutputParserDetailSchema(BaseModel):
    """Schema for detailed output parser information"""
    parser_id: int
    name: str
    description: Optional[str]
    fields: List[OutputParserFieldSchema]
    created_at: Optional[datetime]
    available_parsers: List[Dict[str, Any]]  # Other parsers for references
    
    model_config = ConfigDict(from_attributes=True)


class CreateUpdateOutputParserSchema(BaseModel):
    """Schema for creating or updating an output parser"""
    name: str
    description: Optional[str] = ""
    fields: List[OutputParserFieldSchema]
