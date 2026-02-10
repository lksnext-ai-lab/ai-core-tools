# IA-Core-Tools - AI Toolbox Platform
# Copyright (C) 2024 LKS Next
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# Fix for Windows: psycopg requires SelectorEventLoop instead of ProactorEventLoop
import sys
import asyncio
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from scalar_fastapi import get_scalar_api_reference
import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from config import CLIENT_CONFIG

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
from models.resource import Resource
from models.url import Url

from routers.internal import internal_router
from routers.public.v1 import public_v1_router
from routers.mcp import mcp_router
from utils.provider import initialize_provider, shutdown_provider, get_provider
from lks_idprovider_fastapi.dependencies import get_default_provider

from utils.logger import get_logger
from utils.auth_config import AuthConfig

logger = get_logger(__name__)

# ==================== LIFESPAN CONTEXT MANAGER ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan (startup and shutdown)"""
    # Startup
    try:
        # Load authentication configuration
        AuthConfig.load_config()
        
        # Only initialize EntraID provider if using OIDC mode
        if AuthConfig.LOGIN_MODE == "OIDC":
            logger.info("🔐 Initializing EntraID provider for OIDC authentication")
            await initialize_provider()
            
            # Override the default provider dependency
            app.dependency_overrides[get_default_provider] = get_provider
            logger.info("✅ EntraID provider initialized successfully")
        else:
            logger.warning(
                f"⚠️  Running in {AuthConfig.LOGIN_MODE} mode - "
                "EntraID provider NOT initialized (development/testing only)"
            )
        
        # Initialize checkpointer connection pool for LangGraph agent memory
        from services.agent_cache_service import CheckpointerCacheService
        await CheckpointerCacheService.initialize_pool()

        print("✅ Application startup complete")
    except Exception as e:
        logger.error(f"❌ Error during startup: {e}", exc_info=True)
        print(f"❌ Error during startup: {e}")
        raise

    yield

    # Shutdown
    try:
        # Close checkpointer connection pool
        from services.agent_cache_service import CheckpointerCacheService
        await CheckpointerCacheService.close_pool()

        # Only shutdown provider if it was initialized (OIDC mode)
        if AuthConfig.LOGIN_MODE == "OIDC":
            await shutdown_provider()
            logger.info("✅ EntraID provider shutdown complete")
        print("✅ Application shutdown complete")
    except Exception as e:
        logger.error(f"❌ Error during shutdown: {e}", exc_info=True)
        print(f"❌ Error during shutdown: {e}")


app = FastAPI(
    title=os.getenv('APP_TITLE', f'{CLIENT_CONFIG.client_name} API'),
    description=os.getenv('APP_DESCRIPTION', 'AI Core Tools API'),
    version=os.getenv('APP_VERSION', '0.2.37'),
    lifespan=lifespan
)

# Secure static files serving
# This allows accessing uploaded images via URL (e.g. for multimodal models)
# We serve files from TMP_BASE_FOLDER (default: data/tmp) at /static with signature verification
from utils.config import get_app_config
from utils.security import verify_signature

app_config = get_app_config()
tmp_base_folder = app_config.get('TMP_BASE_FOLDER', 'data/tmp')
os.makedirs(tmp_base_folder, exist_ok=True)

@app.get("/static/{file_path:path}")
async def get_static_file(file_path: str, user: str = None, sig: str = None):
    # Verify signature
    if not user or not sig or not verify_signature(file_path, user, sig):
        raise HTTPException(status_code=403, detail="Invalid signature or missing parameters")
    
    # Prevent directory traversal - check for .. sequences
    if ".." in file_path:
        raise HTTPException(status_code=403, detail="Invalid path")
    
    # Strip leading slashes to prevent absolute path injection
    # os.path.join("data/tmp", "/etc/passwd") would return "/etc/passwd" otherwise
    file_path = file_path.lstrip("/\\")
    
    # Build full path and resolve to absolute
    full_path = os.path.abspath(os.path.join(tmp_base_folder, file_path))
    base_path = os.path.abspath(tmp_base_folder)
    
    # Verify the resolved path is within the allowed directory
    if not full_path.startswith(base_path + os.sep) and full_path != base_path:
        raise HTTPException(status_code=403, detail="Invalid path")

    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found")
        
    return FileResponse(full_path)


# ==================== CORS MIDDLEWARE ====================

FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173')

# Load auth config to check login mode
AuthConfig.load_config()

cors_origins = [
    FRONTEND_URL,  # Main frontend URL from environment
    os.getenv('CORS_ORIGIN_DEV_SERVER', 'http://localhost:5173'),  # React dev server
    os.getenv('CORS_ORIGIN_DEV_SERVER_ALT', 'http://127.0.0.1:5173'),  # Alternative localhost
    os.getenv('CORS_ORIGIN_DOCKER', 'http://localhost:3000'),  # Docker frontend
    os.getenv('CORS_ORIGIN_DOCKER_ALT', 'http://127.0.0.1:3000'),  # Alternative localhost for Docker
]

# In non-OIDC modes (FAKE, etc.), allow additional dev ports for easier testing
if AuthConfig.LOGIN_MODE != "OIDC":
    cors_origins.extend([
        os.getenv('CORS_ORIGIN_DEV_8080', 'http://localhost:8080'),  # Additional dev ports
        os.getenv('CORS_ORIGIN_DEV_8080_ALT', 'http://127.0.0.1:8080'),
        os.getenv('CORS_ORIGIN_VITE_PREVIEW', 'http://localhost:4173'),  # Vite preview
        os.getenv('CORS_ORIGIN_VITE_PREVIEW_ALT', 'http://127.0.0.1:4173'),
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# Mount routers - clean structure with no nesting
app.include_router(internal_router, prefix="/internal")
app.include_router(public_v1_router, prefix="/public/v1")
app.include_router(mcp_router, prefix="/mcp/v1", tags=["MCP"])

# Add client config endpoint
@app.get("/api/internal/client-config")
async def get_client_config():
    """Get client configuration for frontend"""
    return {
        "client_id": CLIENT_CONFIG.client_id,
        "client_name": CLIENT_CONFIG.client_name,
        "oidc_enabled": CLIENT_CONFIG.oidc_enabled,
        "oidc_authority": CLIENT_CONFIG.oidc_authority,
        "oidc_client_id": CLIENT_CONFIG.oidc_client_id
    }

# ==================== CUSTOM OPENAPI DOCS ====================

def get_openapi_internal():
    """Generate OpenAPI schema for internal API only"""
    from fastapi.openapi.utils import get_openapi
    
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=os.getenv('INTERNAL_API_TITLE', 'IA Core Tools - Internal API'),
        version=os.getenv('INTERNAL_API_VERSION', '2.0.0'),
        description=os.getenv('INTERNAL_API_DESCRIPTION', 'Internal API for frontend-backend communication'),
        routes=internal_router.routes,
    )
    return openapi_schema

def get_openapi_public():
    """Generate OpenAPI schema for public API only"""
    from fastapi.openapi.utils import get_openapi
    
    temp_app = FastAPI()
    temp_app.include_router(public_v1_router, prefix="/public/v1")
    
    openapi_schema = get_openapi(
        title=os.getenv('PUBLIC_API_TITLE', 'IA Core Tools - Public API'),
        version=os.getenv('PUBLIC_API_VERSION', '1.0.0'), 
        description=os.getenv('PUBLIC_API_DESCRIPTION', 'Public API for external applications'),
        routes=temp_app.routes,
    )
    return openapi_schema

@app.get("/docs/internal", include_in_schema=False)
async def internal_docs():
    """Swagger UI for internal API"""
    from fastapi.openapi.docs import get_swagger_ui_html
    return get_swagger_ui_html(
        openapi_url=os.getenv('INTERNAL_DOCS_OPENAPI_URL', '/openapi-internal.json'),
        title=os.getenv('INTERNAL_DOCS_TITLE', 'Internal API Docs')
    )

@app.get("/docs/public", include_in_schema=False)
async def public_docs():
    """Swagger UI for public API"""
    from fastapi.openapi.docs import get_swagger_ui_html
    return get_swagger_ui_html(
        openapi_url=os.getenv('PUBLIC_DOCS_OPENAPI_URL', '/openapi-public.json'),
        title=os.getenv('PUBLIC_DOCS_TITLE', 'Public API Docs')
    )

@app.get("/openapi-internal.json", include_in_schema=False)
async def internal_openapi():
    """OpenAPI JSON for internal API"""
    return get_openapi_internal()

@app.get("/openapi-public.json", include_in_schema=False)
async def public_openapi():
    """OpenAPI JSON for public API"""
    return get_openapi_public()

# ==================== SCALAR API REFERENCE ====================
@app.get("/scalar", include_in_schema=False)
async def scalar_html():
    """Scalar API Reference documentation"""
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=f"{CLIENT_CONFIG.client_name} API Reference"
    )

@app.get("/")
async def root():
    return {
        "message": os.getenv('ROOT_MESSAGE', 'IA Core Tools FastAPI Backend'),
        "version": os.getenv('APP_VERSION', '2.0.0'),
        "docs": {
            "internal": os.getenv('INTERNAL_DOCS_PATH', '/docs/internal'),
            "public": os.getenv('PUBLIC_DOCS_PATH', '/docs/public')
        }
    } 
