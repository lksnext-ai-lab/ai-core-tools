from fastapi import APIRouter

# Import all public v1 routers
from .agents import agents_router
from .chat import chat_router
from .files import files_router
from .ocr import ocr_router
from .repositories import repositories_router
from .resources import resources_router
from .silos import silos_router

# Create the main public v1 router
public_v1_router = APIRouter()

# Include sub-routers with proper app structure: /public/v1/app/{app_id}/...
public_v1_router.include_router(agents_router, prefix="/app/{app_id}/agents")
public_v1_router.include_router(chat_router, prefix="/app/{app_id}/chat")
public_v1_router.include_router(files_router, prefix="/app/{app_id}/files")
public_v1_router.include_router(ocr_router, prefix="/app/{app_id}/ocr")
public_v1_router.include_router(repositories_router, prefix="/app/{app_id}/repositories")
public_v1_router.include_router(resources_router, prefix="/app/{app_id}/resources")
public_v1_router.include_router(silos_router, prefix="/app/{app_id}/silos")
