"""Shared helpers/fixtures for the service end-of-service integration tests (step_011)."""

from datetime import datetime, timedelta, timezone

from models.app_collaborator import CollaborationRole, CollaborationStatus
from tests.factories import (
    AIServiceFactory,
    AppCollaboratorFactory,
    AppFactory,
    EmbeddingServiceFactory,
    SandboxServiceFactory,
    UserFactory,
    configure_factories,
)

WARNING_DAYS_ENV = "AICT_SYSTEM_SERVICE_END_OF_SERVICE_WARNING_DAYS"


def future(days: float) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=days)


def past(days: float = 1) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def parse(value):
    return None if value is None else datetime.fromisoformat(value.replace("Z", "+00:00"))


def same_instant(value, expected: datetime) -> bool:
    return abs((parse(value) - expected).total_seconds()) < 1


def headers_for(user) -> dict:
    from utils.local_auth_tokens import mint_access_token

    token, _ = mint_access_token(user.user_id, user.email, user.name)
    return {"Authorization": f"Bearer {token}"}


def member_headers(db, app, role: CollaborationRole) -> dict:
    """Headers of a fresh user holding ``role`` (ACCEPTED) on ``app``."""
    configure_factories(db)
    user = UserFactory()
    AppCollaboratorFactory(app=app, user=user, role=role, status=CollaborationStatus.ACCEPTED,
                           invited_by=app.owner_id)
    db.flush()
    return headers_for(user)


def make_app(db):
    configure_factories(db)
    return AppFactory()


def ai_payload(name="eos-ai", **extra) -> dict:
    return {"name": name, "provider": "OpenAI", "model_name": "gpt-4o", "api_key": "sk-test",  # pragma: allowlist secret
            "base_url": "", **extra}


def embedding_payload(name="eos-emb", **extra) -> dict:
    return {"name": name, "provider": "OpenAI", "model_name": "text-embedding-3-small",
            "api_key": "sk-test", "base_url": "", **extra}  # pragma: allowlist secret


def sandbox_payload(name="eos-sb", **extra) -> dict:
    return {"name": name, "provider": "opensandbox", "api_key": "sb-test", "base_url": "", **extra}  # pragma: allowlist secret


def ai_service(db, app, name=None, eos=None, notice=None, **kw):
    configure_factories(db)
    kwargs = dict(app=app, end_of_service_at=eos, deprecation_notice=notice, description="gpt-4o", **kw)
    if name:
        kwargs["name"] = name
    return AIServiceFactory(**kwargs)


def embedding_service(db, app, name=None, eos=None, notice=None, **kw):
    configure_factories(db)
    kwargs = dict(app=app, end_of_service_at=eos, deprecation_notice=notice, **kw)
    if name:
        kwargs["name"] = name
    return EmbeddingServiceFactory(**kwargs)


def sandbox_service(db, app, name=None, eos=None, notice=None, **kw):
    configure_factories(db)
    kwargs = dict(app=app, end_of_service_at=eos, deprecation_notice=notice, **kw)
    if name:
        kwargs["name"] = name
    return SandboxServiceFactory(**kwargs)


# ---------------------------------------------------------------------------
# Resource builders (ORM level)
# ---------------------------------------------------------------------------

_counter = {"n": 0}


def _n() -> int:
    _counter["n"] += 1
    return _counter["n"]


def make_agent(db, app, service, cls=None, **kw):
    from models.agent import Agent

    n = _n()
    agent = (cls or Agent)(
        name=kw.pop("name", f"eos-agent-{n}"), description="d", system_prompt="s", app_id=app.app_id,
        service_id=service.service_id if service is not None else None, temperature=0.5, **kw,
    )
    db.add(agent)
    db.flush()
    return agent


def make_silo(db, app, **kw):
    from models.silo import Silo

    silo = Silo(name=kw.pop("name", f"eos-silo-{_n()}"), app_id=app.app_id, **kw)
    db.add(silo)
    db.flush()
    return silo


def make_repository(db, app, silo, **kw):
    from models.repository import Repository

    repo = Repository(name=kw.pop("name", f"eos-repo-{_n()}"), app_id=app.app_id, silo_id=silo.silo_id,
                      type="files", status="active", **kw)
    db.add(repo)
    db.flush()
    return repo


def make_summarization_middleware(db, app, service, name=None):
    from models.middleware import Middleware, MiddlewareType

    mw = Middleware(name=name or f"eos-mw-{_n()}", middleware_type=MiddlewareType.SUMMARIZATION, app_id=app.app_id,
                    config={"summarization_model": f"ai_service:{service.service_id}"})
    db.add(mw)
    db.flush()
    return mw


def attach_middleware(db, agent, middleware, order=0):
    from models.middleware import AgentMiddleware

    db.add(AgentMiddleware(agent_id=agent.agent_id, middleware_id=middleware.middleware_id, order=order))
    db.flush()


def make_task(db, app, agent, created_by):
    from models.scheduled_task import ScheduledTask

    task = ScheduledTask(name=f"eos-task-{_n()}", agent_id=agent.agent_id, app_id=app.app_id, created_by=created_by,
                         orchestrator_schedule_name=f"eos-sched-{_n()}-{agent.agent_id}",
                         cron_expression="*/5 * * * *", input={"message": "hi"})
    db.add(task)
    db.flush()
    return task
