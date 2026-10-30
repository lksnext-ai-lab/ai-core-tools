"""Export / import of System One agents and services.

Follows the repo's convention: an exported agent carries the NAME of its services (no ids, never a token) and a
single-agent import resolves them by name in the target app. A full-app export also carries the System One services,
so that importing the agents (always into a NEW app) can link them.
"""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from core.export_constants import validate_export_version
from models.agent import Agent
from models.ai_service import AIService
from models.system_one_agent import SystemOneAgent
from models.system_one_service import SystemOneService
from schemas.export_schemas import AgentExportFileSchema, ExportSystemOneServiceSchema
from schemas.import_schemas import ComponentType, ConflictMode, ImportSummarySchema
from schemas.system_one_schemas import QuestionList, questions_error_message
from services.system_one_service_service import max_concurrency_of, provider_of
from tools import system_one_client
from utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_MAX_STATE_CHARS = 6000


def system_one_export_fields(agent: Any) -> Dict[str, Any]:
    """Extra ``ExportAgentSchema`` fields of a System One agent ({} for any other agent)."""
    if getattr(agent, "type", None) != "system_one_agent":
        return {}
    service = getattr(agent, "system_one_service", None)
    summarizer = getattr(agent, "summarization_service", None)
    return {
        "type": "system_one_agent",
        "questions": agent.questions,
        "max_state_chars": agent.max_state_chars,
        "system_one_service_name": service.name if service else None,
        "summarization_service_name": summarizer.name if summarizer else None,
    }


def export_system_one_service(service: SystemOneService) -> ExportSystemOneServiceSchema:
    return ExportSystemOneServiceSchema(
        name=service.name,
        api_key=None,                                      # never exported
        endpoint=service.endpoint,
        model_name=service.description or "",
        max_concurrency=max_concurrency_of(service),
        provider=provider_of(service),
        end_of_service_at=service.end_of_service_at,
        deprecation_notice=service.deprecation_notice,
    )


def _unique_name(session: Session, model, name: str, app_id: int) -> str:
    candidate, counter = name, 1
    while session.query(model).filter(model.name == candidate, model.app_id == app_id).first():
        candidate = f"{name} ({counter})"
        counter += 1
    return candidate


def import_system_one_service(session: Session, item: ExportSystemOneServiceSchema, app_id: int,
                              api_key: Optional[str] = None) -> Tuple[int, List[str]]:
    """Create a service from a full-app export; the token is only set when the user supplied one."""
    try:
        endpoint = system_one_client.check_base_url(item.endpoint or "")
    except ValueError as exc:
        raise ValueError(f"System One service '{item.name}': {exc}") from exc
    service = SystemOneService(
        app_id=app_id,
        name=_unique_name(session, SystemOneService, item.name, app_id),
        endpoint=endpoint,
        api_key=api_key or None,
        description=item.model_name or None,
        extra_config=json.dumps({"max_concurrency": max(1, item.max_concurrency or 1), "provider": item.provider}),
        create_date=datetime.now(),
        end_of_service_at=item.end_of_service_at,
        deprecation_notice=item.deprecation_notice,
    )
    session.add(service)
    session.flush()
    warnings: List[str] = []
    if not api_key:
        warnings.append(
            f"System One service '{item.name}' was imported without a token: add it in the service settings "
            "if the server requires one"
        )
    return service.service_id, warnings


def import_system_one_agent(
    session: Session,
    export_data: AgentExportFileSchema,
    app_id: int,
    conflict_mode: ConflictMode = ConflictMode.FAIL,
    new_name: Optional[str] = None,
    service_id_map: Optional[Dict[str, int]] = None,
    bundled_services: Optional[List[ExportSystemOneServiceSchema]] = None,
) -> ImportSummarySchema:
    validate_export_version(export_data.metadata.export_version)
    data = export_data.agent
    warnings: List[str] = []

    try:
        questions = TypeAdapter(QuestionList).validate_python(data.questions or [])
    except ValidationError as exc:
        raise ValueError(questions_error_message(exc))

    if not data.system_one_service_name:
        raise ValueError("The export has no System One service reference")
    service_id = (service_id_map or {}).get(data.system_one_service_name)
    if service_id is None:
        service = (session.query(SystemOneService)
                   .filter(SystemOneService.name == data.system_one_service_name, SystemOneService.app_id == app_id)
                   .first())
        bundled = next((b for b in bundled_services or [] if b.name == data.system_one_service_name), None)
        if service is not None:
            service_id = service.service_id          # a service of the same name in this app wins: no copies
        elif bundled is not None:
            service_id, service_warnings = import_system_one_service(session, bundled, app_id)
            warnings.extend(service_warnings)
        else:
            raise ValueError(
                f"System One service '{data.system_one_service_name}' does not exist in this app; "
                "create it before importing the agent"
            )

    summarization_id = None
    if data.summarization_service_name:
        llm = (session.query(AIService)
               .filter(AIService.name == data.summarization_service_name, AIService.app_id == app_id).first())
        if llm is not None:
            summarization_id = llm.service_id
        else:
            warnings.append(
                f"AI service '{data.summarization_service_name}' (summarization) was not found in this app; "
                "long texts will be truncated instead"
            )

    name = data.name
    existing = session.query(Agent).filter(Agent.name == name, Agent.app_id == app_id).first()
    if existing is not None:
        if conflict_mode == ConflictMode.FAIL:
            raise ValueError(f"Agent '{name}' already exists")
        if conflict_mode == ConflictMode.RENAME:
            name = new_name or _unique_name(session, Agent, name, app_id)
        elif not isinstance(existing, SystemOneAgent):
            raise ValueError(f"Agent '{name}' already exists with a different type and cannot be overridden")
    elif new_name:
        name = new_name

    stored_questions = [q.model_dump(mode="json", exclude_none=True) for q in questions]
    max_chars = data.max_state_chars or _DEFAULT_MAX_STATE_CHARS

    if existing is not None and conflict_mode == ConflictMode.OVERRIDE:
        existing.description = data.description
        existing.system_one_service_id = service_id
        existing.summarization_service_id = summarization_id
        existing.questions = stored_questions
        existing.max_state_chars = max_chars
        if data.is_tool is not None:
            existing.is_tool = data.is_tool
        session.commit()
        warnings.append("Existing agent configuration updated.")
        return ImportSummarySchema(
            component_type=ComponentType.AGENT, component_id=existing.agent_id, component_name=name,
            mode=conflict_mode, created=False, conflict_detected=True, warnings=warnings,
            next_steps=["Review updated agent configuration"],
        )

    agent = SystemOneAgent(
        app_id=app_id,
        name=name,
        description=data.description,
        system_one_service_id=service_id,
        summarization_service_id=summarization_id,
        questions=stored_questions,
        max_state_chars=max_chars,
        # files exported before the field existed: like a new System One agent in the form, mostly used as a tool
        is_tool=True if data.is_tool is None else data.is_tool,
        create_date=datetime.now(),
        request_count=0,
    )
    session.add(agent)
    session.flush()
    session.commit()
    return ImportSummarySchema(
        component_type=ComponentType.AGENT, component_id=agent.agent_id, component_name=name, mode=conflict_mode,
        created=True, conflict_detected=existing is not None, warnings=warnings,
        next_steps=["Check the System One service settings (URL and token)"],
    )
