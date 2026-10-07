from typing import Union, List, Dict, Any, Optional
from sqlalchemy.orm import Session
from models.agent import Agent, DEFAULT_AGENT_TEMPERATURE, DEFAULT_MEMORY_SUMMARIZE_THRESHOLD, DEFAULT_PROMPT_TEMPLATE
from models.ocr_agent import OCRAgent
from schemas.agent_schemas import AgentListItemSchema, AgentDetailSchema
from repositories.agent_repository import AgentRepository
from repositories.skill_repository import SkillRepository
from repositories.app_repository import AppRepository
from utils import a2a_config
from utils.logger import get_logger

logger = get_logger(__name__)


def _typed_attr(obj, name: str, expected_type, default=None):
    """Read an optional ORM attribute without leaking dynamic mock values."""
    value = getattr(obj, name, None)
    if value is None:
        return default
    return value if isinstance(value, expected_type) else default


def _build_a2a_urls(app_slug: Optional[str], agent_id: int) -> tuple[Optional[str], Optional[str]]:
    """Return (card_url, rpc_url) for the agent, or (None, None) if the app has no slug.

    Uses the no-request public base URL fallback (FR-11): the ``A2A_PUBLIC_BASE_URL``
    env var, else ``FRONTEND_URL``. The internal agent API has no inbound A2A request
    to fall back to, unlike the A2A router itself.

    ``app_slug``/``agent_id`` are validated with ``isinstance`` (not just truthiness)
    so a non-string/non-int value — e.g. a ``MagicMock`` attribute in a unit test
    that doesn't stub the App lookup — is treated as "no slug" instead of being
    passed into ``urllib.parse.quote``, which only accepts str/bytes.
    """
    if not isinstance(app_slug, str) or not app_slug:
        return None, None
    if not isinstance(agent_id, int) or not agent_id:
        return None, None
    base = a2a_config.public_base_url()
    if not base:
        return None, None
    return (
        a2a_config.agent_card_url(base, app_slug, agent_id),
        a2a_config.agent_rpc_url(base, app_slug, agent_id),
    )


def _serialize_marketplace_profile(profile) -> Optional[Dict[str, Any]]:
    """Serialize an AgentMarketplaceProfile to a dict for schema response."""
    if not profile:
        return None
    published_at = profile.published_at.isoformat() if profile.published_at else None
    updated_at = profile.updated_at.isoformat() if profile.updated_at else None
    return {
        "id": profile.id,
        "agent_id": profile.agent_id,
        "display_name": profile.display_name,
        "short_description": profile.short_description,
        "long_description": profile.long_description,
        "category": profile.category,
        "tags": profile.tags,
        "icon_url": profile.icon_url,
        "cover_image_url": profile.cover_image_url,
        "published_at": published_at,
        "updated_at": updated_at,
    }

class AgentService:

    def get_agents_list(self, db: Session, app_id: int) -> List[AgentListItemSchema]:
        """Get list of agents with AI service details for display"""
        agents = AgentRepository.get_by_app_id(db, app_id)
        
        # Get AI services for this app
        ai_services_dict = AgentRepository.get_ai_services_dict_by_app_id(db, app_id)
        
        result = []
        for agent in agents:
            # Get AI service details if agent has one
            ai_service_info = None
            if hasattr(agent, 'service_id') and agent.service_id and agent.service_id in ai_services_dict:
                ai_service_info = ai_services_dict[agent.service_id]
            
            result.append(AgentListItemSchema(
                agent_id=agent.agent_id,
                name=agent.name,
                description=getattr(agent, 'description', None),
                type=agent.type or "agent",
                is_tool=agent.is_tool or False,
                created_at=agent.create_date,
                request_count=agent.request_count or 0,
                service_id=getattr(agent, 'service_id', None),
                ai_service=ai_service_info,
                marketplace_visibility=(
                    agent.marketplace_visibility.value
                    if hasattr(agent, 'marketplace_visibility') and agent.marketplace_visibility
                    else None
                ),
                a2a_enabled=bool(_typed_attr(agent, 'a2a_enabled', bool, False)),
            ))

        return result

    def get_agents(self, db: Session, app_id: int) -> List[Agent]:
        """Get raw agent objects"""
        return AgentRepository.get_by_app_id(db, app_id)

    def get_tool_agents(self, db: Session, app_id: int, exclude_agent_id: int = None) -> List[Agent]:
        """Get agents that are marked as tools"""
        return AgentRepository.get_tool_agents_by_app_id(db, app_id, exclude_agent_id)

    def get_agent_detail(self, db: Session, app_id: int, agent_id: int) -> Optional[AgentDetailSchema]:
        """Get detailed agent information with form data for editing"""

        # Get agent details, scoped to this app (defense in depth: the router already
        # checks app ownership, but the service must never leak another tenant's agent).
        agent = self._get_agent_for_detail(db, agent_id, app_id)
        if agent_id != 0 and not agent:
            return None
        
        # Get form data for dropdowns
        form_data = self._get_form_data(db, app_id, agent_id)
        
        # Get agent associations
        associations = self._get_agent_associations(db, agent_id)
        
        # Get related information
        silo_info = self._get_silo_info(db, agent) if agent_id != 0 else None
        output_parser_info = self._get_output_parser_info(db, agent) if agent_id != 0 else None

        media_transcription_service_id = _typed_attr(
            agent, "transcription_service_id", int
        )
        media_video_ai_service_id = _typed_attr(agent, "video_ai_service_id", int)
        media_embedding_service_id = _typed_attr(
            agent, "media_embedding_service_id", int
        )
        media_forced_language = _typed_attr(agent, "media_forced_language", str)
        media_chunk_min_duration = _typed_attr(
            agent, "media_chunk_min_duration", int, 30
        )
        media_chunk_max_duration = _typed_attr(
            agent, "media_chunk_max_duration", int, 120
        )
        media_chunk_overlap = _typed_attr(agent, "media_chunk_overlap", int, 5)

        a2a_card_url: Optional[str] = None
        a2a_rpc_url: Optional[str] = None
        if agent_id != 0:
            # Slug-only projection (AppRepository.get_slug_by_id): building the A2A
            # URLs needs nothing else from App, so avoid fetching the full row.
            app_slug = AppRepository(db).get_slug_by_id(app_id)
            a2a_card_url, a2a_rpc_url = _build_a2a_urls(
                app_slug if isinstance(app_slug, str) else None,
                _typed_attr(agent, 'agent_id', int),
            )

        return AgentDetailSchema(
            agent_id=agent.agent_id,
            name=agent.name or "",
            description=getattr(agent, 'description', '') or "",
            system_prompt=getattr(agent, 'system_prompt', '') or "",
            prompt_template=getattr(agent, 'prompt_template', '') or "",
            type=agent.type or "agent",
            is_tool=agent.is_tool or False,
            has_memory=getattr(agent, 'has_memory', False) or False,
            enable_code_interpreter=getattr(agent, 'enable_code_interpreter', False) or False,
            skill_router_enabled=getattr(agent, 'skill_router_enabled', False) or False,
            server_tools=getattr(agent, 'server_tools', None) or [],
            memory_max_messages=getattr(agent, 'memory_max_messages', 20) or 20,
            memory_max_tokens=getattr(agent, 'memory_max_tokens', 4000),
            memory_summarize_threshold=getattr(agent, 'memory_summarize_threshold', DEFAULT_MEMORY_SUMMARIZE_THRESHOLD) or DEFAULT_MEMORY_SUMMARIZE_THRESHOLD,
            service_id=getattr(agent, 'service_id', None),
            sandbox_service_id=getattr(agent, 'sandbox_service_id', None),
            silo_id=getattr(agent, 'silo_id', None),
            output_parser_id=getattr(agent, 'output_parser_id', None),
            temperature=agent.temperature if agent.temperature is not None else DEFAULT_AGENT_TEMPERATURE,
            tool_ids=associations['tool_ids'],
            mcp_config_ids=associations['mcp_ids'],
            skill_ids=associations['skill_ids'],
            created_at=agent.create_date,
            request_count=getattr(agent, 'request_count', 0) or 0,
            # OCR-specific fields
            vision_service_id=getattr(agent, 'vision_service_id', None),
            vision_system_prompt=getattr(agent, 'vision_system_prompt', None),
            text_system_prompt=getattr(agent, 'text_system_prompt', None),
            # Media processing configuration
            transcription_service_id=media_transcription_service_id,
            video_ai_service_id=media_video_ai_service_id,
            media_embedding_service_id=media_embedding_service_id,
            media_forced_language=media_forced_language,
            media_chunk_min_duration=media_chunk_min_duration,
            media_chunk_max_duration=media_chunk_max_duration,
            media_chunk_overlap=media_chunk_overlap,
            # Related information
            silo=silo_info,
            output_parser=output_parser_info,
            # Form data
            ai_services=form_data['ai_services'],
            sandbox_services=form_data['sandbox_services'],
            silos=form_data['silos'],
            output_parsers=form_data['output_parsers'],
            tools=form_data['tools'],
            mcp_configs=form_data['mcp_configs'],
            skills=form_data['skills'],
            # Marketplace
            marketplace_visibility=(
                agent.marketplace_visibility.value
                if hasattr(agent, 'marketplace_visibility') and agent.marketplace_visibility
                else None
            ),
            marketplace_profile=_serialize_marketplace_profile(
                getattr(agent, 'marketplace_profile', None)
            ),
            # RAG retrieval config (step_008)
            rag_k=getattr(agent, 'rag_k', None) if isinstance(getattr(agent, 'rag_k', None), (int, type(None))) else None,
            rag_search_type=getattr(agent, 'rag_search_type', None) if isinstance(getattr(agent, 'rag_search_type', None), (str, type(None))) else None,
            rag_score_threshold=getattr(agent, 'rag_score_threshold', None) if isinstance(getattr(agent, 'rag_score_threshold', None), (float, int, type(None))) else None,
            rag_max_retrieval_calls=getattr(agent, 'rag_max_retrieval_calls', None) if isinstance(getattr(agent, 'rag_max_retrieval_calls', None), (int, type(None))) else None,
            rag_fixed_filters=getattr(agent, 'rag_fixed_filters', None) if isinstance(getattr(agent, 'rag_fixed_filters', None), (list, type(None))) else None,
            # A2A (Agent2Agent protocol) configuration (step_009, FR-3)
            a2a_enabled=bool(_typed_attr(agent, 'a2a_enabled', bool, False)),
            a2a_card_visibility=_typed_attr(agent, 'a2a_card_visibility', str, 'public') or 'public',
            a2a_name_override=_typed_attr(agent, 'a2a_name_override', str),
            a2a_description_override=_typed_attr(agent, 'a2a_description_override', str),
            a2a_skill_tags=_typed_attr(agent, 'a2a_skill_tags', list, []) or [],
            a2a_examples=_typed_attr(agent, 'a2a_examples', list, []) or [],
            a2a_card_url=a2a_card_url,
            a2a_rpc_url=a2a_rpc_url,
        )

    def _get_agent_for_detail(self, db: Session, agent_id: int, app_id: Optional[int] = None):
        """Get agent for detail view, optionally scoped to ``app_id``.

        When ``app_id`` is provided, an agent that exists but belongs to a different
        app is treated as not found (returns ``None``) rather than leaking it.
        """
        if agent_id == 0:
            # New agent
            return type('Agent', (), {
                'agent_id': 0, 'name': '', 'system_prompt': '', 'prompt_template': DEFAULT_PROMPT_TEMPLATE,
                'type': 'agent', 'is_tool': False, 'create_date': None, 'request_count': 0,
                'temperature': DEFAULT_AGENT_TEMPERATURE
            })()
        else:
            # Existing agent - determine if it's OCR agent or regular agent
            agent = self.get_agent(db, agent_id)
            if not agent:
                return None
            if app_id is not None and agent.app_id != app_id:
                return None

            # If it's an OCR agent, get the OCR-specific data
            if agent.type == 'ocr_agent':
                agent = self.get_agent(db, agent_id, 'ocr')
            return agent

    def _get_form_data(self, db: Session, app_id: int, agent_id: int) -> Dict[str, List]:
        """Get form data for dropdowns"""
        return AgentRepository.get_form_data_for_agent(db, app_id, agent_id)

    def _get_agent_associations(self, db: Session, agent_id: int) -> Dict[str, List]:
        """Get agent's current associations"""
        return AgentRepository.get_agent_associations_dict(db, agent_id)

    def _get_silo_info(self, db: Session, agent) -> Optional[Dict[str, Any]]:
        """Get silo information if agent has one"""
        if not hasattr(agent, 'silo_id') or not agent.silo_id:
            return None
        
        return AgentRepository.get_silo_with_metadata_definition(db, agent.silo_id)

    def _get_output_parser_info(self, db: Session, agent) -> Optional[Dict[str, Any]]:
        """Get output parser information if agent has one"""
        if not hasattr(agent, 'output_parser_id') or not agent.output_parser_id:
            return None
        
        return AgentRepository.get_output_parser_info(db, agent.output_parser_id)

    def get_agent(self, db: Session, agent_id: int, agent_type: str = 'basic') -> Union[Agent, OCRAgent]:
        """Get agent by ID and type"""
        return AgentRepository.get_agent_by_id_and_type(db, agent_id, agent_type)
    
    def create_or_update_agent(self, db: Session, agent_data: dict, agent_type: str, user_id: int = None) -> int:
        """Create or update agent"""
        agent_id = agent_data.get('agent_id')

        # If agent_id is 0, treat it as a new agent
        if agent_id == 0:
            agent_id = None

        agent = AgentRepository.get_agent_by_id_and_type(db, agent_id, agent_type) if agent_id else None

        # Defense in depth: never let an update move an existing agent into a different
        # app (the router already verifies ownership, but the service must not silently
        # allow a cross-tenant takeover if ever called without that check upstream).
        # A NULL agent.app_id is also treated as a mismatch (no such thing as a
        # "system" Agent row to legitimately fall through here).
        if agent and agent.app_id != agent_data.get('app_id'):
            raise ValueError(
                f"Agent {agent_id} does not belong to app {agent_data.get('app_id')}"
            )

        is_new_agent = agent is None

        if not agent:
            # Enforce per-app agent limit before creation (SaaS mode only)
            app_id = agent_data.get('app_id')
            if app_id:
                from services.tier_enforcement_service import TierEnforcementService
                TierEnforcementService.check_resource_limit(db, app_id, 'agents')

            # Create the appropriate agent instance based on type
            if agent_type == 'ocr_agent':
                agent = OCRAgent()
            else:
                agent = Agent()

        # Reject any referenced resource id (AI service, silo, output parser, media
        # services) that doesn't belong to this app (or isn't a system-wide resource
        # where that's allowed) before persisting anything — otherwise a caller could
        # point an agent at another tenant's resource (IDOR).
        self._validate_referenced_resource_ids(db, agent_data)

        # Validate rag_fixed_filters fields against the silo's metadata_definition.
        # Fixed filters are only meaningful with a silo; reject them otherwise so a
        # caller never persists dead, never-applied scoping config.
        raw_fixed_filters = agent_data.get('rag_fixed_filters')
        if raw_fixed_filters:
            silo_id = agent_data.get('silo_id') or getattr(agent, 'silo_id', None)
            if not silo_id:
                raise ValueError(
                    "rag_fixed_filters can only be set on an agent that has a silo"
                )
            from tools.vector_stores.metadata_filters import SYSTEM_METADATA_FIELDS
            silo_info = AgentRepository.get_silo_with_metadata_definition(db, silo_id)
            metadata_def = silo_info.get('metadata_definition') if silo_info else None
            # With no metadata_definition only the system fields are filterable.
            declared_fields = frozenset(
                f['name'] for f in ((metadata_def or {}).get('fields') or [])
                if isinstance(f, dict) and f.get('name')
            ) | SYSTEM_METADATA_FIELDS
            unknown = [
                c['field'] for c in raw_fixed_filters
                if isinstance(c, dict) and c.get('field') not in declared_fields
            ]
            if unknown:
                raise ValueError(
                    f"rag_fixed_filters references unknown metadata fields: {unknown}. "
                    f"Allowed fields: {sorted(declared_fields)}"
                )

        update_method = self._update_normal_agent
        update_method(db, agent, agent_data, is_new_agent=is_new_agent)

        # Threshold search needs a threshold value, else it degrades to plain similarity at
        # retrieval. Checked on the merged state (the schema can't see the stored value on a
        # partial update).
        if agent.rag_search_type == 'similarity_score_threshold' and agent.rag_score_threshold is None:
            raise ValueError(
                "rag_score_threshold is required when rag_search_type is "
                "'similarity_score_threshold'"
            )

        # Set type only if it's not already set (OCRAgent sets it in __init__)
        if not hasattr(agent, 'type') or agent.type is None:
            agent.type = agent_type
        
        # Use repository to save the agent
        if agent.agent_id:
            agent = AgentRepository.update(db, agent)
        else:
            agent = AgentRepository.create(db, agent)
        
        # Return the agent ID
        return agent.agent_id

    @staticmethod
    def _validate_owned_resource(resource, app_id: int, field_name: str, allow_system: bool) -> None:
        """Raise ``ValueError`` unless ``resource`` exists and belongs to ``app_id``.

        When ``allow_system`` is true, a resource with ``app_id is None`` (a
        platform/system-wide resource, e.g. AIService or EmbeddingService) is also
        accepted for any app. The error message is intentionally generic — it never
        reveals whether the id exists under a different app.
        """
        if resource is None:
            raise ValueError(f"{field_name} does not exist or does not belong to this app")
        if resource.app_id == app_id:
            return
        if allow_system and resource.app_id is None:
            return
        raise ValueError(f"{field_name} does not exist or does not belong to this app")

    def _validate_referenced_resource_ids(self, db: Session, data: dict) -> None:
        """Ensure every foreign-key id referenced by an agent create/update payload
        belongs to ``data['app_id']`` (or is a system-wide resource, where allowed).

        Without this check, an editor of one app could point their agent at another
        tenant's AI service, silo, output parser, or media-processing service (IDOR).
        ``sandbox_service_id`` is validated separately in ``_update_normal_agent``, and
        ``tool_ids`` / ``mcp_config_ids`` are validated in ``update_agent_tools`` /
        ``update_agent_mcps`` respectively (they're only known after this call).
        """
        app_id = data['app_id']

        service_id = data.get('service_id') or None
        if service_id:
            from repositories.ai_service_repository import AIServiceRepository
            service = AIServiceRepository.get_by_id(db, service_id)
            self._validate_owned_resource(service, app_id, 'service_id', allow_system=True)

        silo_id = data.get('silo_id') or None
        if silo_id:
            from repositories.silo_repository import SiloRepository
            silo = SiloRepository.get_by_id(silo_id, db)
            self._validate_owned_resource(silo, app_id, 'silo_id', allow_system=False)

        output_parser_id = data.get('output_parser_id') or None
        if output_parser_id:
            from repositories.output_parser_repository import OutputParserRepository
            parser = OutputParserRepository().get_by_id(db, output_parser_id)
            self._validate_owned_resource(parser, app_id, 'output_parser_id', allow_system=False)

        # AI-service-backed fields (vision/transcription/video): system-wide services allowed.
        for field_name in ('vision_service_id', 'transcription_service_id', 'video_ai_service_id'):
            value = data.get(field_name) or None
            if value:
                from repositories.ai_service_repository import AIServiceRepository
                service = AIServiceRepository.get_by_id(db, value)
                self._validate_owned_resource(service, app_id, field_name, allow_system=True)

        media_embedding_service_id = data.get('media_embedding_service_id') or None
        if media_embedding_service_id:
            from repositories.embedding_service_repository import EmbeddingServiceRepository
            embedding_service = EmbeddingServiceRepository.get_by_id(db, media_embedding_service_id)
            self._validate_owned_resource(
                embedding_service, app_id, 'media_embedding_service_id', allow_system=True
            )

    @staticmethod
    def _resolve_prompt_template(new_value: Optional[str], current_value: Optional[str]) -> str:
        """Never persist an empty prompt template: it would drop the user's message.

        ``None`` (field not sent, e.g. a partial update) keeps the current template;
        an empty/blank value falls back to the default.
        """
        if new_value is None:
            new_value = current_value
        if not new_value or not new_value.strip():
            return DEFAULT_PROMPT_TEMPLATE
        return new_value

    def _update_normal_agent(self, db: Session, agent: Agent, data: dict, is_new_agent: bool = False):
        """Update agent fields.

        ``is_new_agent`` gates ``app_id`` assignment: it is only ever set at creation
        time. An update must never move an existing agent to a different app's
        ``app_id`` (that would allow a cross-tenant takeover of the agent and the
        AI service/silo it references).
        """
        agent.name = data['name']
        agent.description = data.get('description', '')  # Ensure it's not None
        agent.system_prompt = data.get('system_prompt')
        agent.prompt_template = self._resolve_prompt_template(
            data.get('prompt_template'), agent.prompt_template
        )
        agent.status = data.get('status')
        agent.service_id = data.get('service_id') or None

        # Validate sandbox_service_id belongs to the target app (or is system-scoped)
        # before assigning it. Without this check, any caller could point an agent at
        # a SandboxService owned by a different App, silently running code execution
        # against that other App's provider credentials/endpoint/quota.
        sandbox_service_id = data.get('sandbox_service_id') or None
        if sandbox_service_id:
            from repositories.sandbox_service_repository import SandboxServiceRepository
            sandbox_service = SandboxServiceRepository.get_by_id(db, sandbox_service_id)
            if sandbox_service is None or (
                sandbox_service.app_id is not None and sandbox_service.app_id != data['app_id']
            ):
                raise ValueError(
                    f"sandbox_service_id {sandbox_service_id} does not exist or does not "
                    "belong to this app"
                )
        agent.sandbox_service_id = sandbox_service_id
        if is_new_agent:
            agent.app_id = data['app_id']
        agent.silo_id = data.get('silo_id') or None
        # Handle has_memory field - can be boolean from API or 'on' from form
        has_memory_value = data.get('has_memory')
        if isinstance(has_memory_value, bool):
            agent.has_memory = has_memory_value
        else:
            agent.has_memory = has_memory_value == 'on'

        enable_ci_value = data.get('enable_code_interpreter', False)
        agent.enable_code_interpreter = bool(enable_ci_value)

        # Gated on presence (unlike the sibling enable_code_interpreter field above): the
        # public API route builds its update dict via model_dump(exclude_unset=True), so
        # a partial update that never touches this field must leave the existing value
        # untouched instead of silently resetting it to False.
        if 'skill_router_enabled' in data:
            agent.skill_router_enabled = bool(data['skill_router_enabled'])

        agent.server_tools = data.get('server_tools') or []

        # Memory management fields
        if data.get('memory_max_messages') is not None:
            agent.memory_max_messages = data['memory_max_messages']
        if data.get('memory_max_tokens') is not None:
            agent.memory_max_tokens = data['memory_max_tokens']
        if data.get('memory_summarize_threshold') is not None:
            agent.memory_summarize_threshold = data['memory_summarize_threshold']

        agent.output_parser_id = data.get('output_parser_id') or None

        # Handle temperature field - default to DEFAULT_AGENT_TEMPERATURE if not provided
        agent.temperature = data.get('temperature', DEFAULT_AGENT_TEMPERATURE)

        # OCR-specific fields (only set if the agent is an OCRAgent instance)
        if isinstance(agent, OCRAgent):
            agent.vision_service_id = data.get('vision_service_id')
            agent.vision_system_prompt = data.get('vision_system_prompt')
            agent.text_system_prompt = data.get('text_system_prompt')

        # Media processing configuration (playground media upload). Only touch
        # each field when its key is present in the payload, so callers that
        # build the data dict without media keys don't silently wipe the config.
        if 'transcription_service_id' in data:
            agent.transcription_service_id = data.get('transcription_service_id') or None
        if 'video_ai_service_id' in data:
            agent.video_ai_service_id = data.get('video_ai_service_id') or None
        if 'media_embedding_service_id' in data:
            agent.media_embedding_service_id = data.get('media_embedding_service_id') or None
        if 'media_forced_language' in data:
            agent.media_forced_language = data.get('media_forced_language') or None
        if data.get('media_chunk_min_duration') is not None:
            agent.media_chunk_min_duration = data['media_chunk_min_duration']
        if data.get('media_chunk_max_duration') is not None:
            agent.media_chunk_max_duration = data['media_chunk_max_duration']
        if data.get('media_chunk_overlap') is not None:
            agent.media_chunk_overlap = data['media_chunk_overlap']
        
        # Handle is_tool field - can be boolean from API or 'on' from form
        is_tool_value = data.get('is_tool')
        if isinstance(is_tool_value, bool):
            agent.is_tool = is_tool_value
        else:
            agent.is_tool = is_tool_value == 'on'

        # RAG retrieval config (step_008).
        # New agents: apply opinionated defaults (k=10, max_calls=4) when caller omits the field.
        # Updates: only touch the column when the caller explicitly supplies a value.
        is_new = not getattr(agent, 'agent_id', None)

        if data.get('rag_k') is not None:
            agent.rag_k = data['rag_k']
        elif is_new:
            agent.rag_k = 10

        if data.get('rag_max_retrieval_calls') is not None:
            agent.rag_max_retrieval_calls = data['rag_max_retrieval_calls']
        elif is_new:
            agent.rag_max_retrieval_calls = 4

        if data.get('rag_search_type') is not None:
            agent.rag_search_type = data['rag_search_type']

        # score_threshold and fixed_filters: clear-able via explicit None/empty
        if 'rag_score_threshold' in data:
            agent.rag_score_threshold = data['rag_score_threshold']
        if 'rag_fixed_filters' in data:
            agent.rag_fixed_filters = data['rag_fixed_filters']

        # A2A (Agent2Agent protocol) configuration (step_009, FR-3). Values are already
        # trimmed/capped/deduped by the schema validators; only persist here.
        # Presence-gated (not "truthy"-gated): the schema already validated/normalized
        # each value (including rejecting an explicit null a2a_card_visibility with a
        # 422), so a key present in ``data`` is always safe to assign verbatim. A key
        # the caller never sent is absent from ``data`` entirely (see the router), so
        # it is never touched here — no `or <default>` fallback that could mask an
        # explicit, intentional value.
        if 'a2a_enabled' in data:
            agent.a2a_enabled = bool(data['a2a_enabled'])
        if 'a2a_card_visibility' in data:
            agent.a2a_card_visibility = data['a2a_card_visibility']
        if 'a2a_name_override' in data:
            agent.a2a_name_override = data['a2a_name_override']
        if 'a2a_description_override' in data:
            agent.a2a_description_override = data['a2a_description_override']
        if 'a2a_skill_tags' in data:
            agent.a2a_skill_tags = data['a2a_skill_tags'] or []
        if 'a2a_examples' in data:
            agent.a2a_examples = data['a2a_examples'] or []

    def update_agent_tools(self, db: Session, agent_id: int, tool_ids: list, form_data: dict = None):
        """Update agent tools associations"""
        # Get the agent
        agent = AgentRepository.get_by_id(db, agent_id)
        if not agent:
            return
        
        # Get existing tool associations
        existing_tools = {assoc.tool_id: assoc for assoc in AgentRepository.get_agent_tool_associations(db, agent_id)}

        # Convert tool_ids to set of integers and filter out non-tool agents and agents
        # belonging to a different app (cross-tenant tool attachment / IDOR).
        valid_tool_ids = set(
            AgentRepository.get_valid_tool_ids(db, [int(id) for id in tool_ids if id], agent.app_id)
        )
        
        # Remove associations that are no longer needed
        for tool_id in existing_tools.keys():
            if tool_id not in valid_tool_ids:
                AgentRepository.delete_agent_tool_association(db, existing_tools[tool_id])
        
        # Update or create associations
        for tool_id in valid_tool_ids:
            description = form_data.get(f'tool_description_{tool_id}') if form_data else None
            
            if tool_id in existing_tools:
                # Update existing association
                existing_tools[tool_id].description = description
                db.add(existing_tools[tool_id])
            else:
                # Create new association
                AgentRepository.create_agent_tool_association(db, agent_id, tool_id, description)
        
        db.commit()
    
    def update_agent_mcps(self, db: Session, agent_id: int, mcp_ids: list, form_data: dict = None):
        """Update agent MCP associations"""
        # Get the agent
        agent = AgentRepository.get_by_id(db, agent_id)
        if not agent:
            return
        
        # Convert mcp_ids to list if it's not already
        if isinstance(mcp_ids, str):
            mcp_ids = [mcp_ids]
        elif not isinstance(mcp_ids, list):
            mcp_ids = []

        # Get existing MCP associations
        existing_mcps = {assoc.config_id: assoc for assoc in AgentRepository.get_agent_mcp_associations(db, agent_id)}

        # Convert mcp_ids to set of integers, filtered to configs that exist and belong to
        # this agent's app (cross-tenant MCP config attachment / IDOR otherwise).
        from repositories.mcp_config_repository import MCPConfigRepository
        requested_mcp_ids = [int(id) for id in mcp_ids if id]
        valid_mcp_ids = set(
            MCPConfigRepository.get_valid_config_ids_for_app(db, requested_mcp_ids, agent.app_id)
        )
        
        # Remove associations that are no longer needed
        for mcp_id in existing_mcps.keys():
            if mcp_id not in valid_mcp_ids:
                AgentRepository.delete_agent_mcp_association(db, existing_mcps[mcp_id])
        
        # Update or create associations
        for mcp_id in valid_mcp_ids:
            description = form_data.get(f'mcp_description_{mcp_id}') if form_data else None
            
            if mcp_id in existing_mcps:
                # Update existing association
                existing_mcps[mcp_id].description = description
                db.add(existing_mcps[mcp_id])
            else:
                # Create new association
                AgentRepository.create_agent_mcp_association(db, agent_id, mcp_id, description)
        
        db.commit()

    def update_agent_skills(self, db: Session, agent_id: int, skill_ids: list, form_data: dict = None):
        """Update agent skill associations.

        New attachments must be the app's own skills or enabled, non-colliding system skills (other apps' ids and
        disabled system skills are silently dropped). Existing associations that the client resubmits are RETAINED
        while the skill is still visible to the app, even if it has since been disabled, so disabling a system
        skill never silently detaches it from agents.
        """
        # Get the agent
        agent = AgentRepository.get_by_id(db, agent_id)
        if not agent:
            return

        # Convert skill_ids to list if it's not already
        if isinstance(skill_ids, str):
            skill_ids = [skill_ids]
        elif not isinstance(skill_ids, list):
            skill_ids = []

        # Agents without an app can never attach skills (system skills must not be treated as app skills)
        if agent.app_id is None:
            logger.warning("Agent %s has no app_id; skill associations were not updated", agent_id)
            return

        # Get existing skill associations
        existing_skills = {assoc.skill_id: assoc for assoc in AgentRepository.get_agent_skill_associations(db, agent_id)}

        # Convert skill_ids to set of integers
        requested_skill_ids = {int(id) for id in skill_ids if id}

        # NEW attachments must belong to the agent's app or be enabled system skills; ids from other apps and
        # disabled system skills are silently dropped.
        new_ids = requested_skill_ids - set(existing_skills)
        valid_skill_ids = SkillRepository.get_valid_skill_ids_for_app(db, new_ids, agent.app_id)
        # Existing associations that are resubmitted are RETAINED while the skill is still visible to the app,
        # even if it has been disabled since.
        retained_ids = SkillRepository.get_visible_skill_ids_for_app(
            db, requested_skill_ids & set(existing_skills), agent.app_id
        )
        valid_skill_ids = valid_skill_ids | retained_ids

        # Remove associations that are no longer needed
        for skill_id in existing_skills.keys():
            if skill_id not in valid_skill_ids:
                AgentRepository.delete_agent_skill_association(db, existing_skills[skill_id])

        # Update or create associations
        for skill_id in valid_skill_ids:
            description = form_data.get(f'skill_description_{skill_id}') if form_data else None

            if skill_id in existing_skills:
                # Update existing association
                existing_skills[skill_id].description = description
                db.add(existing_skills[skill_id])
            else:
                # Create new association
                AgentRepository.create_agent_skill_association(db, agent_id, skill_id, description)

        db.commit()

    def delete_agent(self, db: Session, agent_id: int) -> bool:
        """Delete agent"""
        # Scheduled tasks own conversations, files, temp silos and DBOS schedules
        # that a plain FK cascade would leave behind.
        try:
            from services.scheduled_task_service import ScheduledTaskService, default_orchestrator
            ScheduledTaskService(db, default_orchestrator()).purge_for_agent(agent_id)
        except Exception as exc:
            db.rollback()
            import logging
            logging.getLogger(__name__).warning(
                "Could not delete scheduled tasks of agent %s: %s", agent_id, exc
            )
        # Destroy all active sandboxes before deletion (IT-1)
        try:
            from services.sandbox_session_service import sandbox_session_service
            sandbox_session_service.destroy_all_for_agent(agent_id)
        except Exception as exc:
            # Sandbox cleanup failure must not block agent deletion
            import logging
            logging.getLogger(__name__).warning(
                "Could not destroy sandboxes for agent %s during deletion: %s",
                agent_id, exc
            )
        # Clear sandbox DB state for all conversations belonging to this agent
        try:
            from models.conversation import Conversation
            db.query(Conversation).filter(
                Conversation.agent_id == agent_id,
                Conversation.sandbox_session_id.isnot(None),
            ).update(
                {"sandbox_session_id": None, "sandbox_state": None},
                synchronize_session=False,
            )
            db.commit()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Could not clear sandbox DB state for agent %s conversations: %s",
                agent_id, exc
            )
        return AgentRepository.delete_by_id(db, agent_id)

    def _remove_tool_references(self, db: Session, tool_id: int):
        """Remove all tool associations where this agent is used as a tool"""
        AgentRepository.remove_tool_references(db, tool_id)

    def update_agent_prompt(self, db: Session, agent_id: int, prompt_type: str, prompt: str) -> bool:
        """Update agent prompt (system or template)"""
        agent = AgentRepository.get_agent_by_id_and_type(db, agent_id)
        if not agent:
            return False
        
        # Update the appropriate prompt field directly
        if prompt_type == 'system':
            agent.system_prompt = prompt
        elif prompt_type == 'template':
            agent.prompt_template = self._resolve_prompt_template(prompt, None)
        else:
            return False
        
        # Save the changes
        db.commit()
        return True

    def get_agent_playground_data(self, db: Session, agent_id: int) -> Optional[Dict[str, Any]]:
        """Get agent playground data"""
        agent = AgentRepository.get_agent_by_id_and_type(db, agent_id)
        if not agent:
            return None
        
        return {
            "agent_id": agent.agent_id,
            "name": agent.name,
            "type": agent.type,
            "playground_url": f"/playground/{agent_id}"
        }

    def get_agent_analytics(self, db: Session, agent_id: int) -> Optional[Dict[str, Any]]:
        """Get agent analytics data"""
        agent = AgentRepository.get_agent_by_id_and_type(db, agent_id)
        if not agent:
            return None
        
        # Return analytics data with actual implementation placeholder
        return {
            "agent_id": agent.agent_id,
            "name": agent.name,
            "request_count": agent.request_count or 0,
            "analytics_data": "Analytics feature coming soon"
        } 
