from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from routers.internal import internal_router
from routers.public.v1 import public_v1_router

# Import key models to ensure SQLAlchemy relationships are configured  
from models.app import App
from models.user import User
from models.app_collaborator import AppCollaborator
from models.mcp_config import MCPConfig
from models.agent import Agent
from models.api_key import APIKey
from models.silo import Silo
from models.domain import Domain
from models.repository import Repository
from models.ai_service import AIService
from models.embedding_service import EmbeddingService
from models.output_parser import OutputParser
from models.subscription import Subscription
from models.api_usage import APIUsage
from models.resource import Resource
from models.url import Url

app = FastAPI(
    title="IA-Core-Tools API", 
    description="Backend API for IA-Core-Tools application",
    version="2.0.0",
    docs_url=None, 
    redoc_url=None, 
    openapi_url=None
)

# Mount routers
app.include_router(internal_router, prefix="/internal", tags=["internal"])
app.include_router(public_v1_router, prefix="/api/v1", tags=["public-v1"])

# Create separate OpenAPI schemas for internal and public APIs
def get_internal_openapi():
    """Generate OpenAPI schema for internal API only"""
    if app.internal_openapi_schema:
        return app.internal_openapi_schema
    
    # Create a temporary app with only internal routes
    internal_app = FastAPI(title="Internal API", version="2.0.0")
    internal_app.include_router(internal_router, prefix="/internal")
    
    openapi_schema = get_openapi(
        title="IA-Core-Tools Internal API",
        version="2.0.0",
        description="Internal API for frontend-backend communication",
        routes=internal_app.routes,
    )
    
    app.internal_openapi_schema = openapi_schema
    return openapi_schema

def get_public_openapi():
    """Generate OpenAPI schema for public API only"""  
    if app.public_openapi_schema:
        return app.public_openapi_schema
    
    # Create a temporary app with only public routes
    public_app = FastAPI(title="Public API v1", version="1.0.0")
    public_app.include_router(public_v1_router, prefix="/api/v1")
    
    openapi_schema = get_openapi(
        title="IA-Core-Tools Public API v1",
        version="1.0.0", 
        description="Public API for external applications",
        routes=public_app.routes,
    )
    
    app.public_openapi_schema = openapi_schema
    return openapi_schema

# Initialize schema cache
app.internal_openapi_schema = None
app.public_openapi_schema = None

# Custom docs endpoints
@app.get("/docs/internal", include_in_schema=False)
def custom_internal_docs():
    return get_swagger_ui_html(openapi_url="/openapi/internal.json", title="Internal API Docs")

@app.get("/openapi/internal.json", include_in_schema=False)
def internal_openapi():
    return get_internal_openapi()

@app.get("/docs/public", include_in_schema=False)
def custom_public_docs():
    return get_swagger_ui_html(openapi_url="/openapi/public.json", title="Public API Docs")

@app.get("/openapi/public.json", include_in_schema=False)
def public_openapi():
    return get_public_openapi() 