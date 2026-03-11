"""
Schema validation tests for MCP Config Export/Import (Phase 4).

Tests:
1. ExportMCPConfigSchema validation
2. MCPConfigExportFileSchema structure
3. Config JSON validation
4. Field requirements

Usage:
    pytest backend/tests/test_mcp_config_export_import_schemas.py -v
"""

import pytest
import json
from datetime import datetime
from pydantic import ValidationError

from schemas.export_schemas import (
    ExportMetadataSchema,
    ExportMCPConfigSchema,
    MCPConfigExportFileSchema
)
from schemas.import_schemas import ConflictMode, ComponentType


class TestExportMCPConfigSchema:
    """Test ExportMCPConfigSchema validation."""
    
    def test_valid_mcp_config_schema(self):
        """Test creating valid MCP config export schema."""
        config_dict = {
            "url": "http://localhost:8080/mcp",
            "timeout": 30,
            "headers": {"User-Agent": "TestClient/1.0"}
        }
        
        schema = ExportMCPConfigSchema(
            name="Test MCP Server",
            description="Test MCP configuration",
            config=json.dumps(config_dict)
        )
        
        assert schema.name == "Test MCP Server"
        assert schema.description == "Test MCP configuration"
        assert schema.config is not None
        
        # Verify config is valid JSON
        parsed_config = json.loads(schema.config)
        assert parsed_config["url"] == "http://localhost:8080/mcp"
        assert parsed_config["timeout"] == 30
    
    def test_required_name_field(self):
        """Test that name field is required."""
        with pytest.raises(ValidationError):
            ExportMCPConfigSchema(
                description="Config without name",
                config=json.dumps({})
            )
    
    def test_name_min_length(self):
        """Test name minimum length validation."""
        with pytest.raises(ValidationError):
            ExportMCPConfigSchema(
                name="",  # Empty name should fail
                description="Test",
                config=json.dumps({})
            )
    
    def test_name_max_length(self):
        """Test name maximum length validation."""
        with pytest.raises(ValidationError):
            ExportMCPConfigSchema(
                name="x" * 256,  # Exceeds max_length=255
                description="Test",
                config=json.dumps({})
            )
    
    def test_optional_description(self):
        """Test that description is optional."""
        schema = ExportMCPConfigSchema(
            name="Test Config",
            config=json.dumps({"url": "http://test.com"})
        )
        
        assert schema.name == "Test Config"
        assert schema.description is None
    
    def test_optional_config(self):
        """Test that config is optional."""
        schema = ExportMCPConfigSchema(
            name="Minimal Config",
            description="Config without JSON"
        )
        
        assert schema.name == "Minimal Config"
        assert schema.config is None
    
    def test_config_with_nested_structure(self):
        """Test config with nested JSON structure."""
        config_dict = {
            "url": "http://localhost:8080",
            "timeout": 30,
            "headers": {
                "User-Agent": "TestClient/1.0",
                "Accept": "application/json"
            },
            "features": {
                "streaming": True,
                "batch_size": 100,
                "retry": {
                    "max_attempts": 3,
                    "backoff": "exponential"
                }
            }
        }
        
        schema = ExportMCPConfigSchema(
            name="Complex Config",
            description="Config with nested structure",
            config=json.dumps(config_dict)
        )
        
        parsed = json.loads(schema.config)
        assert parsed["features"]["streaming"] is True
        assert parsed["features"]["retry"]["max_attempts"] == 3


class TestMCPConfigExportFileSchema:
    """Test MCPConfigExportFileSchema validation."""
    
    def test_valid_export_file_schema(self):
        """Test creating valid export file schema."""
        metadata = ExportMetadataSchema(
            export_version="1.0.0",
            export_date=datetime(2026, 2, 9, 10, 30, 0),
            exported_by="test_user",
            source_app_id=1
        )
        
        config_dict = {
            "url": "http://localhost:8080/mcp",
            "timeout": 30
        }
        
        mcp_config = ExportMCPConfigSchema(
            name="Production MCP Server",
            description="Production MCP configuration",
            config=json.dumps(config_dict)
        )
        
        export_file = MCPConfigExportFileSchema(
            metadata=metadata,
            mcp_config=mcp_config
        )
        
        assert export_file.metadata.export_version == "1.0.0"
        assert export_file.metadata.exported_by == "test_user"
        assert export_file.metadata.source_app_id == 1
        assert export_file.mcp_config.name == "Production MCP Server"
        assert export_file.mcp_config.config is not None
    
    def test_serialization_to_json(self):
        """Test serialization of export file to JSON."""
        metadata = ExportMetadataSchema(
            export_version="1.0.0",
            export_date=datetime(2026, 2, 9, 12, 0, 0),
            exported_by="admin",
            source_app_id=5
        )
        
        config_dict = {
            "url": "http://api.example.com/mcp",
            "timeout": 60,
            "headers": {"Authorization": "Bearer token"}
        }
        
        mcp_config = ExportMCPConfigSchema(
            name="API MCP Server",
            description="External API MCP config",
            config=json.dumps(config_dict)
        )
        
        export_file = MCPConfigExportFileSchema(
            metadata=metadata,
            mcp_config=mcp_config
        )
        
        # Serialize to dict
        data = export_file.model_dump(mode='json')
        
        assert data['metadata']['export_version'] == "1.0.0"
        assert data['metadata']['exported_by'] == "admin"
        assert data['metadata']['source_app_id'] == 5
        assert data['mcp_config']['name'] == "API MCP Server"
        assert data['mcp_config']['config'] is not None
        
        # Verify config is valid JSON string in output
        assert isinstance(data['mcp_config']['config'], str)
        parsed = json.loads(data['mcp_config']['config'])
        assert parsed['url'] == "http://api.example.com/mcp"
    
    def test_deserialization_from_json(self):
        """Test deserialization from JSON dict."""
        json_data = {
            "metadata": {
                "export_version": "1.0.0",
                "export_date": "2026-02-09T15:30:00",
                "exported_by": "test_user",
                "source_app_id": 10
            },
            "mcp_config": {
                "name": "Development MCP",
                "description": "Dev environment MCP config",
                "config": json.dumps({
                    "url": "http://localhost:3000/mcp",
                    "timeout": 15,
                    "debug": True
                })
            }
        }
        
        export_file = MCPConfigExportFileSchema(**json_data)
        
        assert export_file.metadata.export_version == "1.0.0"
        assert export_file.mcp_config.name == "Development MCP"
        assert export_file.mcp_config.description == "Dev environment MCP config"
        
        # Verify config can be parsed
        config = json.loads(export_file.mcp_config.config)
        assert config["url"] == "http://localhost:3000/mcp"
        assert config["debug"] is True
    
    def test_export_without_config_json(self):
        """Test export with None config (minimal export)."""
        metadata = ExportMetadataSchema(
            export_version="1.0.0",
            export_date=datetime.now(),
            exported_by="user",
            source_app_id=1
        )
        
        mcp_config = ExportMCPConfigSchema(
            name="Minimal MCP",
            description="Config without JSON",
            config=None
        )
        
        export_file = MCPConfigExportFileSchema(
            metadata=metadata,
            mcp_config=mcp_config
        )
        
        assert export_file.mcp_config.config is None
        
        # Should serialize without error
        data = export_file.model_dump(mode='json')
        assert data['mcp_config']['config'] is None


class TestSanitizedExport:
    """Test that exports should not contain sensitive data."""
    
    def test_sanitized_config_structure(self):
        """Test export structure for sanitized config."""
        # This test documents the expected structure after sanitization
        sanitized_config = {
            "url": "http://localhost:8080/mcp",
            "timeout": 30,
            "headers": {
                "User-Agent": "TestClient/1.0"
                # Note: No Authorization header (sanitized)
            },
            "features": {
                "streaming": True
            }
            # Note: No api_key, token, password fields (sanitized)
        }
        
        schema = ExportMCPConfigSchema(
            name="Sanitized Config",
            description="Config after sanitization",
            config=json.dumps(sanitized_config)
        )
        
        parsed = json.loads(schema.config)
        
        # Verify no sensitive keys present
        assert "api_key" not in parsed
        assert "apiKey" not in parsed
        assert "token" not in parsed
        assert "password" not in parsed
        assert "secret" not in parsed
        assert "Authorization" not in parsed.get("headers", {})
        
        # Verify non-sensitive data preserved
        assert "url" in parsed
        assert "timeout" in parsed
        assert "features" in parsed


class TestComponentTypeEnum:
    """Test ComponentType enum includes MCP_CONFIG."""
    
    def test_mcp_config_in_component_type(self):
        """Test that MCP_CONFIG is in ComponentType enum."""
        assert ComponentType.MCP_CONFIG == "mcp_config"
        assert ComponentType.MCP_CONFIG in list(ComponentType)


class TestConflictModeEnum:
    """Test ConflictMode enum for import operations."""
    
    def test_conflict_modes_available(self):
        """Test all conflict modes are available."""
        assert ConflictMode.FAIL == "fail"
        assert ConflictMode.RENAME == "rename"
        assert ConflictMode.OVERRIDE == "override"
        
        # Verify all modes are in enum
        modes = list(ConflictMode)
        assert ConflictMode.FAIL in modes
        assert ConflictMode.RENAME in modes
        assert ConflictMode.OVERRIDE in modes
