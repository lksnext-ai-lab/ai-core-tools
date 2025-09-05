from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
import os

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

from routers.internal import internal_router
from routers.public.v1 import public_v1_router
from routers.auth import auth_router
from routers.internal.admin import router as admin_router
from routers.internal.version import version_router

app = FastAPI(
    title="IA Core Tools API",
    description="Modern FastAPI backend for IA Core Tools",
    version="2.0.0"
)

# Get CORS origins from environment variables
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173')
DEVELOPMENT_MODE = os.getenv('DEVELOPMENT_MODE', 'false').lower() == 'true'

# Configure CORS origins based on environment
cors_origins = [
    FRONTEND_URL,  # Main frontend URL from environment
]

# Add development origins if in development mode
if DEVELOPMENT_MODE:
    cors_origins.extend([
        "http://localhost:5173",  # React dev server
        "http://127.0.0.1:5173",  # Alternative localhost
        "http://localhost:3000",  # Docker frontend
        "http://127.0.0.1:3000",  # Alternative localhost for Docker
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# Mount routers
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])  # Add auth router
app.include_router(internal_router, prefix="/internal")
app.include_router(admin_router, prefix="/internal")  # Admin routes are under /internal/admin
app.include_router(public_v1_router, prefix="/public/v1")
app.include_router(version_router, prefix="/internal")  # Version routes under /internal

# ==================== CUSTOM OPENAPI DOCS ====================

def get_openapi_internal():
    """Generate OpenAPI schema for internal API only"""
    from fastapi.openapi.utils import get_openapi
    
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="IA Core Tools - Internal API",
        version="2.0.0",
        description="Internal API for frontend-backend communication",
        routes=internal_router.routes,
    )
    return openapi_schema

def get_openapi_public():
    """Generate OpenAPI schema for public API only"""
    from fastapi.openapi.utils import get_openapi
    
    temp_app = FastAPI()
    temp_app.include_router(public_v1_router, prefix="/public/v1")
    
    openapi_schema = get_openapi(
        title="IA Core Tools - Public API",
        version="1.0.0", 
        description="Public API for external applications",
        routes=temp_app.routes,
    )
    return openapi_schema

@app.get("/docs/internal", include_in_schema=False)
async def internal_docs():
    """Swagger UI for internal API"""
    from fastapi.openapi.docs import get_swagger_ui_html
    return get_swagger_ui_html(
        openapi_url="/openapi-internal.json",
        title="Internal API Docs"
    )

@app.get("/docs/public", include_in_schema=False)
async def public_docs():
    """Swagger UI for public API"""
    from fastapi.openapi.docs import get_swagger_ui_html
    return get_swagger_ui_html(
        openapi_url="/openapi-public.json",
        title="Public API Docs"
    )

@app.get("/openapi-internal.json", include_in_schema=False)
async def internal_openapi():
    """OpenAPI JSON for internal API"""
    return get_openapi_internal()

@app.get("/openapi-public.json", include_in_schema=False)
async def public_openapi():
    """OpenAPI JSON for public API"""
    return get_openapi_public()

@app.get("/")
async def root():
    return {
        "message": "IA Core Tools FastAPI Backend",
        "version": "2.0.0",
        "docs": {
            "internal": "/docs/internal",
            "public": "/docs/public"
        }
    } 