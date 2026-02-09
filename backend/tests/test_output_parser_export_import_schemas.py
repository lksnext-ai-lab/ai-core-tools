"""
Schema validation tests for Output Parser Export/Import (Phase 3).

Tests:
1. ExportOutputParserFieldSchema validation
2. ExportOutputParserSchema validation
3. OutputParserExportFileSchema structure
4. Field type validation
5. Parser references in fields

Usage:
    pytest backend/tests/test_output_parser_export_import_schemas.py -v
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from schemas.export_schemas import (
    ExportMetadataSchema,
    ExportOutputParserFieldSchema,
    ExportOutputParserSchema,
    OutputParserExportFileSchema
)
from schemas.import_schemas import ConflictMode, ComponentType


class TestExportOutputParserFieldSchema:
    """Test ExportOutputParserFieldSchema validation."""
    
    def test_valid_simple_field(self):
        """Test creating valid simple field."""
        field = ExportOutputParserFieldSchema(
            name="username",
            type="str",
            description="User's username"
        )
        
        assert field.name == "username"
        assert field.type == "str"
        assert field.description == "User's username"
        assert field.parser_id is None
        assert field.list_item_type is None
    
    def test_field_with_parser_reference(self):
        """Test field with parser reference."""
        field = ExportOutputParserFieldSchema(
            name="address",
            type="parser",
            description="User address",
            parser_id=42
        )
        
        assert field.type == "parser"
        assert field.parser_id == 42
    
    def test_field_with_list(self):
        """Test field with list type."""
        field = ExportOutputParserFieldSchema(
            name="tags",
            type="list",
            description="List of tags",
            list_item_type="str"
        )
        
        assert field.type == "list"
        assert field.list_item_type == "str"
    
    def test_field_with_list_of_parsers(self):
        """Test field with list of parsers."""
        field = ExportOutputParserFieldSchema(
            name="contacts",
            type="list",
            description="List of contacts",
            list_item_type="parser",
            list_item_parser_id=99
        )
        
        assert field.type == "list"
        assert field.list_item_type == "parser"
        assert field.list_item_parser_id == 99


class TestExportOutputParserSchema:
    """Test ExportOutputParserSchema validation."""
    
    def test_valid_output_parser_schema(self):
        """Test creating valid output parser export schema."""
        schema = ExportOutputParserSchema(
            name="User Parser",
            description="Parse user data",
            fields=[
                ExportOutputParserFieldSchema(
                    name="name",
                    type="str",
                    description="User name"
                ),
                ExportOutputParserFieldSchema(
                    name="age",
                    type="int",
                    description="User age"
                )
            ]
        )
        
        assert schema.name == "User Parser"
        assert schema.description == "Parse user data"
        assert len(schema.fields) == 2
        assert schema.fields[0].name == "name"
        assert schema.fields[1].type == "int"
    
    def test_empty_fields_list(self):
        """Test parser with no fields."""
        schema = ExportOutputParserSchema(
            name="Empty Parser",
            description="Parser with no fields",
            fields=[]
        )
        
        assert schema.name == "Empty Parser"
        assert len(schema.fields) == 0
    
    def test_required_name_field(self):
        """Test that name field is required."""
        with pytest.raises(ValidationError):
            ExportOutputParserSchema(
                description="Parser without name",
                fields=[]
            )
    
    def test_name_min_length(self):
        """Test name minimum length validation."""
        with pytest.raises(ValidationError):
            ExportOutputParserSchema(
                name="",  # Empty name should fail
                description="Test",
                fields=[]
            )
    
    def test_name_max_length(self):
        """Test name maximum length validation."""
        with pytest.raises(ValidationError):
            ExportOutputParserSchema(
                name="x" * 256,  # Exceeds max_length=255
                description="Test",
                fields=[]
            )
    
    def test_optional_description(self):
        """Test that description is optional."""
        schema = ExportOutputParserSchema(
            name="Test Parser",
            fields=[]
        )
        
        assert schema.name == "Test Parser"
        assert schema.description is None


class TestOutputParserExportFileSchema:
    """Test OutputParserExportFileSchema validation."""
    
    def test_valid_export_file_schema(self):
        """Test creating valid export file schema."""
        metadata = ExportMetadataSchema(
            export_version="1.0.0",
            export_date=datetime(2026, 2, 9, 10, 30, 0),
            exported_by="test_user",
            source_app_id=1
        )
        
        parser = ExportOutputParserSchema(
            name="Contact Parser",
            description="Parse contact information",
            fields=[
                ExportOutputParserFieldSchema(
                    name="email",
                    type="str",
                    description="Email address"
                ),
                ExportOutputParserFieldSchema(
                    name="phone",
                    type="str",
                    description="Phone number"
                )
            ]
        )
        
        export_file = OutputParserExportFileSchema(
            metadata=metadata,
            output_parser=parser
        )
        
        assert export_file.metadata.export_version == "1.0.0"
        assert export_file.metadata.exported_by == "test_user"
        assert export_file.metadata.source_app_id == 1
        assert export_file.output_parser.name == "Contact Parser"
        assert len(export_file.output_parser.fields) == 2
    
    def test_serialization_to_json(self):
        """Test serialization of export file to JSON."""
        metadata = ExportMetadataSchema(
            export_version="1.0.0",
            export_date=datetime(2026, 2, 9, 12, 0, 0),
            exported_by="admin",
            source_app_id=5
        )
        
        parser = ExportOutputParserSchema(
            name="Product Parser",
            description="Parse product data",
            fields=[
                ExportOutputParserFieldSchema(
                    name="sku",
                    type="str",
                    description="Product SKU"
                ),
                ExportOutputParserFieldSchema(
                    name="price",
                    type="float",
                    description="Product price"
                )
            ]
        )
        
        export_file = OutputParserExportFileSchema(
            metadata=metadata,
            output_parser=parser
        )
        
        # Serialize to dict
        data = export_file.model_dump(mode='json')
        
        assert data['metadata']['export_version'] == "1.0.0"
        assert data['metadata']['exported_by'] == "admin"
        assert data['metadata']['source_app_id'] == 5
        assert data['output_parser']['name'] == "Product Parser"
        assert len(data['output_parser']['fields']) == 2
        assert data['output_parser']['fields'][0]['name'] == "sku"
        assert data['output_parser']['fields'][1]['type'] == "float"
    
    def test_deserialization_from_json(self):
        """Test deserialization from JSON dict."""
        json_data = {
            "metadata": {
                "export_version": "1.0.0",
                "export_date": "2026-02-09T15:30:00",
                "exported_by": "test_user",
                "source_app_id": 10
            },
            "output_parser": {
                "name": "Order Parser",
                "description": "Parse order data",
                "fields": [
                    {
                        "name": "order_id",
                        "type": "str",
                        "description": "Order ID"
                    },
                    {
                        "name": "total",
                        "type": "float",
                        "description": "Order total"
                    },
                    {
                        "name": "items",
                        "type": "list",
                        "description": "Order items",
                        "list_item_type": "str"
                    }
                ]
            }
        }
        
        export_file = OutputParserExportFileSchema(**json_data)
        
        assert export_file.metadata.export_version == "1.0.0"
        assert export_file.output_parser.name == "Order Parser"
        assert len(export_file.output_parser.fields) == 3
        assert export_file.output_parser.fields[2].type == "list"
        assert export_file.output_parser.fields[2].list_item_type == "str"


class TestComponentTypeEnum:
    """Test ComponentType enum includes OUTPUT_PARSER."""
    
    def test_output_parser_in_component_type(self):
        """Test that OUTPUT_PARSER is in ComponentType enum."""
        assert ComponentType.OUTPUT_PARSER == "output_parser"
        assert ComponentType.OUTPUT_PARSER in list(ComponentType)
