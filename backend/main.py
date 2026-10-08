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

# psycopg requires SelectorEventLoop on Windows (not ProactorEventLoop).
import sys
import asyncio
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


import errno
from contextlib import asynccontextmanager
from sqlalchemy.exc import TimeoutError as SQLAlchemyPoolTimeout
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from scalar_fastapi import get_scalar_api_reference
import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from config import CLIENT_CONFIG

from models.app import App
from models.user import User
from models.app_collaborator import AppCollaborator
from models.mcp_config import MCPConfig
from models.agent import Agent
from models.api_key import APIKey
from models.silo import Silo
from models.domain import Domain
from models.domain_url import DomainUrl
from models.crawl_policy import CrawlPolicy
from models.crawl_job import CrawlJob
from models.repository import Repository
from models.ai_service import AIService
from models.embedding_service import EmbeddingService
from models.output_parser import OutputParser
from models.resource import Resource

from routers.internal import internal_router
from routers.public.v1 import public_v1_router
from routers.mcp import mcp_router
from routers.a2a_server import a2a_router
from utils.provider import initialize_provider, shutdown_provider, get_provider
from lks_idprovider_fastapi.dependencies import get_default_provider

from utils.logger import get_logger
from utils.auth_config import AuthConfig
from utils.secret_key import validate_secret_key
from deployment_mode import is_saas_mode, validate_saas_env

logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    try:
        validate_secret_key()

        from scheduling.periodic_agent_task import initialize_dbos
        app.state.dbos_enabled = await initialize_dbos()

        if is_saas_mode():
            validate_saas_env()
            logger.info("SaaS mode: environment validation passed")
            from db.database import SessionLocal
            from services.tier_config_seeder import seed_default_tier_configs
            _db = SessionLocal()
            try:
                seed_default_tier_configs(_db)
            finally:
                _db.close()

        # Unconditional (not SaaS-only): system skills are seeded in every deployment mode.
        from db.database import SessionLocal
        from services.system_skills_seeder import seed_system_skills
        _db = SessionLocal()
        try:
            seed_system_skills(_db)
        except Exception:
            logger.error("system_skills_seeder: failed to seed system skills at startup", exc_info=True)
        finally:
            _db.close()

        AuthConfig.load_config()

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
        
        if AuthConfig.LOGIN_MODE == "LOCAL":
            from db.database import SessionLocal as _SessionLocal
            from services.auth.omniadmin_bootstrap import bootstrap_omniadmins
            _bootstrap_db = _SessionLocal()
            try:
                await bootstrap_omniadmins(_bootstrap_db)
            except Exception as _bootstrap_exc:
                logger.error(
                    "omniadmin_bootstrap: unexpected error during startup bootstrap — %s",
                    _bootstrap_exc,
                    exc_info=True,
                )
            finally:
                _bootstrap_db.close()

        from services.agent_cache_service import CheckpointerCacheService
        await CheckpointerCacheService.initialize_pool()

        # A2A (step_017): build the process-wide runtime unconditionally --
        # even when A2A_ENABLED=false, since the kill switch is per request
        # (routers/a2a_server/router.py) and the maintenance worker (step_018)
        # needs a handler to drive cancellation through.
        try:
            from services.a2a_server.executor import MattinAgentExecutor
            from services.a2a_server.runtime import (
                build_a2a_runtime,
                configure_sdk_logging,
                set_runtime,
            )
            from utils.a2a_config import get_a2a_config

            configure_sdk_logging()
            # get_a2a_config() itself logs a warning if A2A_ROOT_AGENT is set
            # but malformed (utils/a2a_config.py's _get_root_agent), and
            # clamps/warns if the worker stream cap is >= uvicorn's own
            # --limit-concurrency (fix round 1, HIGH-3).
            a2a_cfg = get_a2a_config()
            set_runtime(build_a2a_runtime(MattinAgentExecutor()))
            logger.info("A2A runtime initialized (enabled=%s)", a2a_cfg.enabled)
        except Exception:
            logger.error("Failed to initialize the A2A runtime at startup", exc_info=True)
            # LOW (fix round 1): A2A is opt-in; a build failure while it is
            # globally disabled (A2A_ENABLED=false) must never take the rest
            # of the application down with it. `get_runtime()` stays `None`
            # in that case -- every A2A route already treats that the same
            # as the kill switch (uniform 404).
            if get_a2a_config().enabled:
                raise

        # Start crawl workers (job executor + scheduler)
        from services.crawl.worker import start_crawl_workers, stop_crawl_workers
        crawl_tasks = await start_crawl_workers(app)
        app.state.crawl_tasks = crawl_tasks

        from services.file_cleanup_worker import start_file_cleanup_worker
        app.state.file_cleanup_task = start_file_cleanup_worker()

        # A2A maintenance worker (step_018, AD-10): always runs, even when
        # A2A_ENABLED=false, so retention keeps happening regardless of the
        # per-request kill switch.
        from services.a2a_server.maintenance_worker import start_a2a_maintenance_worker
        app.state.a2a_maintenance_task = start_a2a_maintenance_worker()

        from services.sharepoint.worker import start_sharepoint_worker
        app.state.sharepoint_tasks = await start_sharepoint_worker()

        print("✅ Application startup complete")
    except Exception as e:
        logger.error(f"❌ Error during startup: {e}", exc_info=True)
        print(f"❌ Error during startup: {e}")
        raise

    yield

    try:
        # LOW (fix round 1): each shutdown step gets its own try/except, so
        # one failing step (e.g. a hung worker) never skips the rest --
        # previously these shared one outer try, with only a handful of
        # steps individually guarded.
        try:
            from scheduling.periodic_agent_task import shutdown_dbos
            shutdown_dbos()
        except Exception as exc:
            logger.warning("DBOS shutdown failed: %s", exc, exc_info=True)

        try:
            crawl_tasks = getattr(app.state, 'crawl_tasks', None)
            if crawl_tasks:
                from services.crawl.worker import stop_crawl_workers
                await stop_crawl_workers(crawl_tasks)
        except Exception as exc:
            logger.warning("Crawl worker shutdown failed: %s", exc, exc_info=True)

        try:
            file_cleanup_task = getattr(app.state, 'file_cleanup_task', None)
            if file_cleanup_task is not None:
                from services.file_cleanup_worker import stop_file_cleanup_worker
                await stop_file_cleanup_worker(file_cleanup_task)
        except Exception as exc:
            logger.warning("File cleanup worker shutdown failed: %s", exc, exc_info=True)

        try:
            sharepoint_tasks = getattr(app.state, 'sharepoint_tasks', None)
            if sharepoint_tasks:
                from services.sharepoint.worker import stop_sharepoint_worker
                await stop_sharepoint_worker(sharepoint_tasks)
        except Exception as exc:
            logger.warning("SharePoint worker shutdown failed: %s", exc, exc_info=True)

        try:
            a2a_maintenance_task = getattr(app.state, 'a2a_maintenance_task', None)
            if a2a_maintenance_task is not None:
                from services.a2a_server.maintenance_worker import stop_a2a_maintenance_worker
                await stop_a2a_maintenance_worker(a2a_maintenance_task)
        except Exception as exc:
            logger.warning("A2A maintenance worker shutdown failed: %s", exc, exc_info=True)

        try:
            from services.a2a_server.runtime import close_runtime

            await close_runtime()
        except Exception as exc:
            logger.warning("A2A runtime shutdown (close_runtime) failed: %s", exc, exc_info=True)

        try:
            from services.agent_cache_service import CheckpointerCacheService
            await CheckpointerCacheService.close_pool()
        except Exception as exc:
            logger.warning("Checkpointer pool shutdown failed: %s", exc, exc_info=True)

        try:
            from tools.langsmith_config import flush_langsmith_clients, clear_client_cache
            flush_langsmith_clients()
            clear_client_cache()
        except Exception as exc:
            logger.warning("LangSmith flush during shutdown failed: %s", exc)

        try:
            if AuthConfig.LOGIN_MODE == "OIDC":
                await shutdown_provider()
                logger.info("✅ EntraID provider shutdown complete")
        except Exception as exc:
            logger.warning("OIDC provider shutdown failed: %s", exc, exc_info=True)
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

from utils.config import get_app_config
from utils.security import verify_static_access

app_config = get_app_config()
tmp_base_folder = app_config.get('TMP_BASE_FOLDER', 'data/tmp')
os.makedirs(tmp_base_folder, exist_ok=True)

@app.get("/static/{file_path:path}")
async def get_static_file(
    file_path: str,
    user: str = None,
    sig: str = None,
    filename: str = None,
    exp: str | None = None,
):
    # `exp` is declared as `str | None` (not `int | None`) so that a malformed value
    # (e.g. "abc") fails the same 403 path below instead of FastAPI's 422 validation
    # error, which would otherwise leak which query params are well-formed.
    # All parsing, missing-parameter checks and the expiring/legacy dispatch live in
    # verify_static_access, which collapses every failure reason to a single False.
    if not verify_static_access(file_path, user, sig, exp, filename):
        raise HTTPException(status_code=403, detail="Invalid signature or missing parameters")

    if ".." in file_path:  # directory traversal guard
        raise HTTPException(status_code=403, detail="Invalid path")

    # os.path.join ignores the base when the suffix starts with '/' — strip it.
    file_path = file_path.lstrip("/\\")

    full_path = os.path.abspath(os.path.join(tmp_base_folder, file_path))
    base_path = os.path.abspath(tmp_base_folder)

    if not full_path.startswith(base_path + os.sep) and full_path != base_path:
        raise HTTPException(status_code=403, detail="Invalid path")

    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found")

    download_filename = filename or os.path.basename(full_path)
    return FileResponse(full_path, filename=download_filename)


FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173')
AuthConfig.load_config()

cors_origins = [
    FRONTEND_URL,
    os.getenv('CORS_ORIGIN_DEV_SERVER', 'http://localhost:5173'),
    os.getenv('CORS_ORIGIN_DEV_SERVER_ALT', 'http://127.0.0.1:5173'),
    os.getenv('CORS_ORIGIN_DOCKER', 'http://localhost:3000'),
    os.getenv('CORS_ORIGIN_DOCKER_ALT', 'http://127.0.0.1:3000'),
]

if AuthConfig.LOGIN_MODE != "OIDC":
    cors_origins.extend([
        os.getenv('CORS_ORIGIN_DEV_8080', 'http://localhost:8080'),
        os.getenv('CORS_ORIGIN_DEV_8080_ALT', 'http://127.0.0.1:8080'),
        os.getenv('CORS_ORIGIN_VITE_PREVIEW', 'http://localhost:4173'),
        os.getenv('CORS_ORIGIN_VITE_PREVIEW_ALT', 'http://127.0.0.1:4173'),
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(OSError)
async def _oserror_handler(_request: Request, exc: OSError) -> JSONResponse:
    """Surface disk-full conditions to clients as 507 Insufficient Storage.

    Without this handler, ``OSError(ENOSPC)`` leaking out of a handler
    becomes an opaque 500 ("Internal server error") that doesn't tell the
    operator what's actually wrong. Other ``OSError`` codes (permission,
    not-found, …) fall through to the framework default.
    """
    if exc.errno == errno.ENOSPC:
        logger.error("Server storage exhausted (ENOSPC): %s", exc)
        return JSONResponse(
            status_code=507,
            content={
                "detail": (
                    "Server storage exhausted. The operator must free disk "
                    "space on the host before retrying."
                )
            },
        )
    raise exc


@app.exception_handler(SQLAlchemyPoolTimeout)
async def _db_pool_timeout_handler(_request: Request, exc: SQLAlchemyPoolTimeout) -> JSONResponse:
    """Map DB connection-pool exhaustion to 503 with Retry-After instead of an opaque 500."""
    logger.error("Database connection pool exhausted: %s", exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "Service temporarily unavailable, please retry shortly."},
        headers={"Retry-After": "5"},
    )


# Mount routers - clean structure with no nesting
app.include_router(internal_router, prefix="/internal")
app.include_router(public_v1_router, prefix="/public/v1")
app.include_router(mcp_router, prefix="/mcp/v1", tags=["MCP"])
# A2A (step_017, AD-14): mounted at root -- its routes carry their own
# absolute paths (/a2a/v1/... and the root /.well-known/agent-card.json).
app.include_router(a2a_router)

@app.get("/api/internal/client-config")
async def get_client_config():
    """Return client configuration for the frontend."""
    return {
        "client_id": CLIENT_CONFIG.client_id,
        "client_name": CLIENT_CONFIG.client_name,
        "oidc_enabled": CLIENT_CONFIG.oidc_enabled,
        "oidc_authority": CLIENT_CONFIG.oidc_authority,
        "oidc_client_id": CLIENT_CONFIG.oidc_client_id
    }

_openapi_internal_schema = None
_openapi_public_schema = None

def _routes_with_prefix(prefix: str):
    """Routes of the app whose full path starts with ``prefix``.

    Since FastAPI 0.137 ``app.routes`` is a tree (included routers are kept as
    nodes), so it is walked with ``iter_route_contexts`` to get every route
    with its effective path.
    """
    from fastapi.routing import iter_route_contexts

    return [
        route for route in iter_route_contexts(app.routes)
        if route.path and route.path.startswith(prefix)
    ]

def get_openapi_internal():
    """Generate OpenAPI schema for internal API only."""
    global _openapi_internal_schema
    from fastapi.openapi.utils import get_openapi
    
    if _openapi_internal_schema:
        return _openapi_internal_schema
    
    internal_routes = _routes_with_prefix('/internal')
    
    _openapi_internal_schema = get_openapi(
        title=os.getenv('INTERNAL_API_TITLE', 'IA Core Tools - Internal API'),
        version=os.getenv('INTERNAL_API_VERSION', '2.0.0'),
        description=os.getenv('INTERNAL_API_DESCRIPTION', 'Internal API for frontend-backend communication'),
        routes=internal_routes,
    )
    return _openapi_internal_schema

def get_openapi_public():
    """Generate OpenAPI schema for public API only."""
    global _openapi_public_schema
    from fastapi.openapi.utils import get_openapi
    
    if _openapi_public_schema:
        return _openapi_public_schema
    
    public_routes = _routes_with_prefix('/public')
    
    _openapi_public_schema = get_openapi(
        title=os.getenv('PUBLIC_API_TITLE', 'IA Core Tools - Public API'),
        version=os.getenv('PUBLIC_API_VERSION', '1.0.0'), 
        description=os.getenv('PUBLIC_API_DESCRIPTION', 'Public API for external applications'),
        routes=public_routes,
    )
    return _openapi_public_schema

@app.get("/docs/internal", include_in_schema=False)
async def internal_docs():
    """Swagger UI for the internal API."""
    from fastapi.openapi.docs import get_swagger_ui_html
    return get_swagger_ui_html(
        openapi_url=os.getenv('INTERNAL_DOCS_OPENAPI_URL', '/openapi-internal.json'),
        title=os.getenv('INTERNAL_DOCS_TITLE', 'Internal API Docs')
    )

@app.get("/docs/public", include_in_schema=False)
async def public_docs():
    """Swagger UI for the public API."""
    from fastapi.openapi.docs import get_swagger_ui_html
    return get_swagger_ui_html(
        openapi_url=os.getenv('PUBLIC_DOCS_OPENAPI_URL', '/openapi-public.json'),
        title=os.getenv('PUBLIC_DOCS_TITLE', 'Public API Docs')
    )

@app.get("/openapi-internal.json", include_in_schema=False)
async def internal_openapi():
    return get_openapi_internal()

@app.get("/openapi-public.json", include_in_schema=False)
async def public_openapi():
    return get_openapi_public()

@app.get("/scalar", include_in_schema=False)
async def scalar_html():
    """Scalar API reference."""
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
