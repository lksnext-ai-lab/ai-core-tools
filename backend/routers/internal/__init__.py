from fastapi import APIRouter

# Import all internal routers
from .agents import agents_router
from .ai_services import ai_services_router
from .api_keys import api_keys_router
from .apps import apps_router
from .chat import chat_router
from .collaboration import collaboration_router
from .domains import domains_router
from .embedding_services import embedding_services_router
from .mcp_configs import mcp_configs_router
from .ocr import ocr_router
from .output_parsers import output_parsers_router
from .repositories import repositories_router
from .silos import silos_router

# Create the main internal router
internal_router = APIRouter(tags=["internal"])

# Include all sub-routers
internal_router.include_router(agents_router, prefix="/agents")
internal_router.include_router(ai_services_router, prefix="/ai-services")
internal_router.include_router(api_keys_router, prefix="/api-keys")
internal_router.include_router(apps_router, prefix="/apps")
internal_router.include_router(chat_router, prefix="/chat")
internal_router.include_router(collaboration_router, prefix="/collaboration")
internal_router.include_router(domains_router, prefix="/domains")
internal_router.include_router(embedding_services_router, prefix="/embedding-services")
internal_router.include_router(mcp_configs_router, prefix="/mcp-configs")
internal_router.include_router(ocr_router, prefix="/ocr")
internal_router.include_router(output_parsers_router, prefix="/output-parsers")
internal_router.include_router(repositories_router, prefix="/repositories")
internal_router.include_router(silos_router, prefix="/silos")