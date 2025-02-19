from pydantic import BaseModel, Field

class DomainSchema(BaseModel):
    domain_id: int | None = Field(default=None, description="Domain ID")
    name: str = Field(..., description="Domain name")
    description: str | None = Field(default=None, description="Domain description")
    base_url: str = Field(..., description="Base URL")
    content_tag: str | None = Field(default=None, description="HTML content tag")
    content_class: str | None = Field(default=None, description="HTML content class")
    content_id: str | None = Field(default=None, description="HTML content ID")
    app_id: int | None = Field(default=None, description="Associated App ID")
    silo_id: int = Field(..., description="Associated Silo ID")
    
    class Config:
        from_attributes = True 
