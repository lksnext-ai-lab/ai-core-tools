from functools import lru_cache
from typing import Optional

from a2a.server.apps.jsonrpc.fastapi_app import A2AFastAPIApplication
from a2a.server.apps.jsonrpc.jsonrpc_app import CallContextBuilder
from a2a.server.context import ServerCallContext
from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from db.database import get_db
from models.agent import Agent
from models.app import App
from repositories.mcp_server_repository import AppSlugRepository
from routers.controls.origins import enforce_allowed_origins
from routers.controls.rate_limit import enforce_app_rate_limit
from routers.public.v1.auth import (
    create_api_key_user_context,
    get_api_key_auth,
    validate_api_key_for_app,
)
from services.a2a_agent_card_service import A2AAgentCardService
from services.a2a_agent_executor import MattinA2AAgentExecutor
from services.a2a_task_store import MattinA2ATaskStore
from utils.logger import get_logger

logger = get_logger(__name__)

a2a_router = APIRouter()


class MattinA2ACallContextBuilder(CallContextBuilder):
    """Build ServerCallContext from request.state prepared by the router."""

    def build(self, request: Request) -> ServerCallContext:
        state = getattr(request.state, "a2a_state", {})
        return ServerCallContext(state={"a2a": state})


@lru_cache(maxsize=1)
def get_a2a_request_handler() -> DefaultRequestHandler:
    return DefaultRequestHandler(
        agent_executor=MattinA2AAgentExecutor(),
        task_store=MattinA2ATaskStore(),
    )


def _resolve_enabled_agent_by_app_id(db: Session, app_id: int, agent_id: int) -> tuple[App, Agent]:
    app = db.query(App).filter(App.app_id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")

    agent = db.query(Agent).filter(Agent.agent_id == agent_id, Agent.app_id == app.app_id).first()
    if not agent or not agent.a2a_enabled:
        raise HTTPException(status_code=404, detail="A2A agent not found")
    return app, agent


def _resolve_enabled_agent_by_slug(db: Session, app_slug: str, agent_id: int) -> tuple[App, Agent]:
    app = AppSlugRepository.get_by_slug(db, app_slug)
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    return _resolve_enabled_agent_by_app_id(db, app.app_id, agent_id)


def _build_rpc_url(request: Request, *, app_slug: Optional[str], app_id: Optional[int], agent_id: int) -> str:
    base_url = str(request.base_url).rstrip("/")
    if app_slug is not None:
        return f"{base_url}/a2a/v1/apps/{app_slug}/agents/{agent_id}"
    return f"{base_url}/a2a/v1/id/{app_id}/agents/{agent_id}"


def _build_application(
    request: Request,
    app: App,
    agent: Agent,
    *,
    app_slug: Optional[str] = None,
    app_id: Optional[int] = None,
) -> A2AFastAPIApplication:
    rpc_url = _build_rpc_url(request, app_slug=app_slug, app_id=app_id, agent_id=agent.agent_id)
    card = A2AAgentCardService.build_agent_card(app=app, agent=agent, rpc_url=rpc_url)
    return A2AFastAPIApplication(
        agent_card=card,
        http_handler=get_a2a_request_handler(),
        context_builder=MattinA2ACallContextBuilder(),
    )


def _set_request_state(
    request: Request,
    app: App,
    agent: Agent,
    api_key: str,
    api_key_auth,
    db: Session,
) -> None:
    request.state.a2a_state = {
        "app_id": app.app_id,
        "agent_id": agent.agent_id,
        "api_key": api_key,
        "api_key_id": api_key_auth.key_id,
        "conversation_id": None,
        "user_context": create_api_key_user_context(app.app_id, api_key),
        "base_url": str(request.base_url).rstrip("/"),
        "db_session": db,
    }


async def _handle_rpc_request(
    request: Request,
    response: Response,
    db: Session,
    app: App,
    agent: Agent,
    api_key: str,
    *,
    app_slug: Optional[str] = None,
    app_id: Optional[int] = None,
) -> Response:
    api_key_auth = validate_api_key_for_app(app.app_id, api_key, db)
    enforce_allowed_origins(app.app_id, request, db)
    enforce_app_rate_limit(app.app_id, response, db)
    _set_request_state(request, app, agent, api_key, api_key_auth, db)
    application = _build_application(request, app, agent, app_slug=app_slug, app_id=app_id)
    return await application._handle_requests(request)


@a2a_router.get("/.well-known/a2a/apps/{app_slug}/agents/{agent_id}")
async def get_agent_card_by_slug(
    app_slug: str,
    agent_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    app, agent = _resolve_enabled_agent_by_slug(db, app_slug, agent_id)
    application = _build_application(request, app, agent, app_slug=app_slug)
    return await application._handle_get_agent_card(request)


@a2a_router.get("/.well-known/a2a/id/{app_id}/agents/{agent_id}")
async def get_agent_card_by_id(
    app_id: int,
    agent_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    app, agent = _resolve_enabled_agent_by_app_id(db, app_id, agent_id)
    application = _build_application(request, app, agent, app_id=app_id)
    return await application._handle_get_agent_card(request)


@a2a_router.post("/a2a/v1/apps/{app_slug}/agents/{agent_id}")
async def rpc_by_slug(
    app_slug: str,
    agent_id: int,
    request: Request,
    response: Response,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db),
):
    app, agent = _resolve_enabled_agent_by_slug(db, app_slug, agent_id)
    return await _handle_rpc_request(
        request,
        response,
        db,
        app,
        agent,
        api_key,
        app_slug=app_slug,
    )


@a2a_router.post("/a2a/v1/id/{app_id}/agents/{agent_id}")
async def rpc_by_id(
    app_id: int,
    agent_id: int,
    request: Request,
    response: Response,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db),
):
    app, agent = _resolve_enabled_agent_by_app_id(db, app_id, agent_id)
    return await _handle_rpc_request(
        request,
        response,
        db,
        app,
        agent,
        api_key,
        app_id=app_id,
    )
