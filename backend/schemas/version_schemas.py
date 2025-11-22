"""
Pydantic schemas for version management API.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Literal

class VersionResponseSchema(BaseModel):
    """Response schema for version information"""
    version: str = Field(..., description="Current version in semantic versioning format (MAJOR.MINOR.PATCH)")
    name: str = Field(..., description="Project name")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "version": "0.3.7",
                "name": "ai-core-tools"
            }
        }
    }

class VersionBumpRequestSchema(BaseModel):
    """Request schema for bumping version"""
    bump_type: Literal["major", "minor", "patch"] = Field(
        ..., 
        description="Type of version bump to perform"
    )
    
    @field_validator('bump_type')
    @classmethod
    def validate_bump_type(cls, v: str) -> str:
        """Ensure bump_type is lowercase"""
        return v.lower()
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "bump_type": "patch",
                    "description": "Bump patch version (e.g., 0.3.7 -> 0.3.8) for bug fixes"
                },
                {
                    "bump_type": "minor",
                    "description": "Bump minor version (e.g., 0.3.7 -> 0.4.0) for new features"
                },
                {
                    "bump_type": "major",
                    "description": "Bump major version (e.g., 0.3.7 -> 1.0.0) for breaking changes"
                }
            ]
        }
    }

class VersionBumpResponseSchema(BaseModel):
    """Response schema for version bump operation"""
    old_version: str = Field(..., description="Version before the bump")
    new_version: str = Field(..., description="Version after the bump")
    message: str = Field(..., description="Success message")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "old_version": "0.3.7",
                "new_version": "0.3.8",
                "message": "Version successfully bumped from 0.3.7 to 0.3.8"
            }
        }
    }
