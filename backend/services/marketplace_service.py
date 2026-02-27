import uuid
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, func, case, desc, asc
from typing import List, Optional, Tuple
from datetime import datetime, timezone

from models.agent import Agent, MarketplaceVisibility
from models.agent_marketplace_profile import AgentMarketplaceProfile
from models.conversation import Conversation, ConversationSource
from models.app_collaborator import AppCollaborator, CollaborationStatus
from models.app import App
from schemas.marketplace_schemas import (
    MarketplaceAgentCardSchema,
    MarketplaceAgentDetailSchema,
    MarketplaceProfileSchema,
    MarketplaceProfileCreateUpdateSchema,
    MarketplaceConversationSchema,
)
from utils.logger import get_logger

logger = get_logger(__name__)


class MarketplaceService:
    """Service for marketplace business logic: catalog, agent detail, profile CRUD, conversations."""

    @staticmethod
    def _get_user_app_ids(db: Session, user_id: int) -> set:
        """
        Get the set of app_ids where the user is owner or an accepted collaborator.
        """
        # Apps owned by the user
        owned = db.query(App.app_id).filter(App.owner_id == user_id).all()
        owned_ids = {row.app_id for row in owned}

        # Apps where user is an accepted collaborator
        collab = (
            db.query(AppCollaborator.app_id)
            .filter(
                AppCollaborator.user_id == user_id,
                AppCollaborator.status == CollaborationStatus.ACCEPTED,
            )
            .all()
        )
        collab_ids = {row.app_id for row in collab}

        return owned_ids | collab_ids

    # ------------------------------------------------------------------
    # 1. Catalog – helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_visibility_filter(query, user_app_ids: set, my_apps_only: bool):
        """Apply visibility scoping to a catalog query."""
        if my_apps_only:
            return query.filter(Agent.app_id.in_(user_app_ids)) if user_app_ids else None

        if user_app_ids:
            return query.filter(
                or_(
                    Agent.marketplace_visibility == MarketplaceVisibility.PUBLIC,
                    Agent.app_id.in_(user_app_ids),
                )
            )
        return query.filter(
            Agent.marketplace_visibility == MarketplaceVisibility.PUBLIC
        )

    @staticmethod
    def _apply_search_filter(query, search: str):
        """Apply ILIKE search across display_name, short_description, agent name, tags."""
        pattern = f"%{search}%"
        return query.filter(
            or_(
                AgentMarketplaceProfile.display_name.ilike(pattern),
                AgentMarketplaceProfile.short_description.ilike(pattern),
                Agent.name.ilike(pattern),
                func.cast(AgentMarketplaceProfile.tags, func.text()).ilike(pattern),
            )
        )

    @staticmethod
    def _apply_sort(query, sort_by: str, search: Optional[str]):
        """Apply sorting to a catalog query."""
        resolved_name = func.coalesce(AgentMarketplaceProfile.display_name, Agent.name)

        if sort_by == "alphabetical":
            return query.order_by(asc(resolved_name))
        if sort_by == "newest":
            return query.order_by(desc(AgentMarketplaceProfile.published_at))

        # "relevance"
        if search:
            relevance = case(
                (AgentMarketplaceProfile.display_name.ilike(search), 1),
                (Agent.name.ilike(search), 2),
                else_=3,
            )
            return query.order_by(asc(relevance), asc(resolved_name))
        return query.order_by(desc(AgentMarketplaceProfile.published_at))

    # ------------------------------------------------------------------
    # 1. Catalog
    # ------------------------------------------------------------------

    @staticmethod
    def get_marketplace_catalog(
        db: Session,
        user_id: int,
        search: Optional[str] = None,
        category: Optional[str] = None,
        my_apps_only: bool = False,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "relevance",
    ) -> Tuple[List[MarketplaceAgentCardSchema], int]:
        """
        Query agents visible to this user in the marketplace.

        Returns a tuple of (list of card schemas, total count).
        """
        user_app_ids = MarketplaceService._get_user_app_ids(db, user_id)

        # Base query: agent + profile + app
        query = (
            db.query(Agent, AgentMarketplaceProfile, App)
            .join(AgentMarketplaceProfile, Agent.agent_id == AgentMarketplaceProfile.agent_id)
            .join(App, Agent.app_id == App.app_id)
            .filter(
                Agent.is_tool == False,  # noqa: E712
                Agent.marketplace_visibility != MarketplaceVisibility.UNPUBLISHED,
            )
        )

        # Visibility scoping
        query = MarketplaceService._apply_visibility_filter(query, user_app_ids, my_apps_only)
        if query is None:
            return [], 0

        # Search filter
        if search:
            query = MarketplaceService._apply_search_filter(query, search)

        # Category filter
        if category:
            query = query.filter(AgentMarketplaceProfile.category == category)

        total = query.count()

        # Sorting
        query = MarketplaceService._apply_sort(query, sort_by, search)

        # Pagination
        offset = (page - 1) * page_size
        results = query.offset(offset).limit(page_size).all()

        # Build response schemas
        cards: List[MarketplaceAgentCardSchema] = []
        for agent, profile, app in results:
            cards.append(
                MarketplaceAgentCardSchema(
                    agent_id=agent.agent_id,
                    display_name=profile.display_name or agent.name,
                    short_description=profile.short_description,
                    category=profile.category,
                    tags=profile.tags,
                    icon_url=profile.icon_url,
                    app_name=app.name,
                    app_id=app.app_id,
                    has_knowledge_base=agent.silo_id is not None,
                    published_at=profile.published_at,
                )
            )

        return cards, total

    # ------------------------------------------------------------------
    # 2. Agent detail
    # ------------------------------------------------------------------

    @staticmethod
    def get_marketplace_agent_detail(
        db: Session,
        agent_id: int,
        user_id: int,
    ) -> Optional[MarketplaceAgentDetailSchema]:
        """
        Retrieve a single agent's marketplace detail.

        Returns None if the agent is not found, not published, or the user
        does not have access.
        Never exposes system_prompt, service_id, temperature, or internal config.
        """
        agent = (
            db.query(Agent)
            .options(
                joinedload(Agent.marketplace_profile),
                joinedload(Agent.app),
            )
            .filter(Agent.agent_id == agent_id)
            .first()
        )

        if not agent or not agent.marketplace_profile:
            return None

        # Visibility check
        if agent.marketplace_visibility == MarketplaceVisibility.UNPUBLISHED:
            return None

        if agent.marketplace_visibility == MarketplaceVisibility.PRIVATE:
            user_app_ids = MarketplaceService._get_user_app_ids(db, user_id)
            if agent.app_id not in user_app_ids:
                return None

        profile = agent.marketplace_profile
        return MarketplaceAgentDetailSchema(
            agent_id=agent.agent_id,
            display_name=profile.display_name or agent.name,
            short_description=profile.short_description,
            long_description=profile.long_description,
            category=profile.category,
            tags=profile.tags,
            icon_url=profile.icon_url,
            cover_image_url=profile.cover_image_url,
            app_name=agent.app.name,
            app_id=agent.app.app_id,
            has_knowledge_base=agent.silo_id is not None,
            has_memory=bool(agent.has_memory),
            published_at=profile.published_at,
        )

    # ------------------------------------------------------------------
    # 3. Visibility update
    # ------------------------------------------------------------------

    @staticmethod
    def update_marketplace_visibility(
        db: Session,
        agent_id: int,
        app_id: int,
        visibility_str: str,
    ) -> Agent:
        """
        Update an agent's marketplace_visibility.

        Raises ValueError if the agent is a tool agent and visibility is not UNPUBLISHED.
        """
        agent = (
            db.query(Agent)
            .options(joinedload(Agent.marketplace_profile))
            .filter(Agent.agent_id == agent_id, Agent.app_id == app_id)
            .first()
        )
        if not agent:
            raise ValueError(f"Agent {agent_id} not found in app {app_id}")

        visibility = MarketplaceVisibility(visibility_str)

        if agent.is_tool and visibility != MarketplaceVisibility.UNPUBLISHED:
            raise ValueError("Tool agents cannot be published to the marketplace")

        agent.marketplace_visibility = visibility

        # Set published_at on first publish
        if visibility in (MarketplaceVisibility.PRIVATE, MarketplaceVisibility.PUBLIC):
            profile = agent.marketplace_profile
            if profile and profile.published_at is None:
                profile.published_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(agent)

        logger.info(
            f"Agent {agent_id} marketplace visibility updated to {visibility_str}"
        )
        return agent

    # ------------------------------------------------------------------
    # 4. Profile create / update
    # ------------------------------------------------------------------

    @staticmethod
    def create_or_update_marketplace_profile(
        db: Session,
        agent_id: int,
        app_id: int,
        profile_data: MarketplaceProfileCreateUpdateSchema,
    ) -> AgentMarketplaceProfile:
        """
        Create or update the marketplace profile for an agent.
        Only non-None fields from profile_data are applied on update.
        """
        agent = (
            db.query(Agent)
            .options(joinedload(Agent.marketplace_profile))
            .filter(Agent.agent_id == agent_id, Agent.app_id == app_id)
            .first()
        )
        if not agent:
            raise ValueError(f"Agent {agent_id} not found in app {app_id}")

        profile = agent.marketplace_profile

        if profile:
            # Update only provided (non-None) fields
            update_data = profile_data.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                setattr(profile, key, value)
        else:
            # Create new profile
            profile = AgentMarketplaceProfile(
                agent_id=agent_id,
                **profile_data.model_dump(exclude_unset=True),
            )
            db.add(profile)

        db.commit()
        db.refresh(profile)

        logger.info(f"Marketplace profile upserted for agent {agent_id}")
        return profile

    # ------------------------------------------------------------------
    # 5. Profile read (EDITOR+ management view)
    # ------------------------------------------------------------------

    @staticmethod
    def get_marketplace_profile(
        db: Session,
        agent_id: int,
        app_id: int,
    ) -> Optional[MarketplaceProfileSchema]:
        """
        Get the marketplace profile for an agent (EDITOR+ management view).
        """
        profile = (
            db.query(AgentMarketplaceProfile)
            .join(Agent, Agent.agent_id == AgentMarketplaceProfile.agent_id)
            .filter(
                AgentMarketplaceProfile.agent_id == agent_id,
                Agent.app_id == app_id,
            )
            .first()
        )
        if not profile:
            return None

        return MarketplaceProfileSchema.model_validate(profile)

    # ------------------------------------------------------------------
    # 6. Marketplace conversations (consumer list)
    # ------------------------------------------------------------------

    @staticmethod
    def get_marketplace_conversations(
        db: Session,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[MarketplaceConversationSchema], int]:
        """
        List a consumer's marketplace conversations, ordered by updated_at DESC.
        Resolves agent display name and icon from the marketplace profile.
        """
        base_query = (
            db.query(Conversation, Agent, AgentMarketplaceProfile)
            .join(Agent, Conversation.agent_id == Agent.agent_id)
            .outerjoin(
                AgentMarketplaceProfile,
                Agent.agent_id == AgentMarketplaceProfile.agent_id,
            )
            .filter(
                Conversation.user_id == user_id,
                Conversation.source == ConversationSource.MARKETPLACE,
            )
        )

        total = base_query.count()

        results = (
            base_query
            .order_by(desc(Conversation.updated_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

        conversations: List[MarketplaceConversationSchema] = []
        for conv, agent, profile in results:
            conversations.append(
                MarketplaceConversationSchema(
                    conversation_id=conv.conversation_id,
                    agent_id=conv.agent_id,
                    title=conv.title,
                    created_at=conv.created_at,
                    updated_at=conv.updated_at,
                    last_message=conv.last_message,
                    message_count=conv.message_count,
                    agent_display_name=(
                        profile.display_name if profile and profile.display_name else agent.name
                    ),
                    agent_icon_url=profile.icon_url if profile else None,
                )
            )

        return conversations, total

    # ------------------------------------------------------------------
    # 7. Create marketplace conversation
    # ------------------------------------------------------------------

    @staticmethod
    def create_marketplace_conversation(
        db: Session,
        agent_id: int,
        user_id: int,
        title: Optional[str] = None,
    ) -> Conversation:
        """
        Create a new marketplace conversation.

        Verifies:
        - Agent exists and is published (visibility != UNPUBLISHED)
        - User has access (PUBLIC → any user; PRIVATE → user is member of agent's App)

        Returns the created Conversation.
        """
        agent = (
            db.query(Agent)
            .options(joinedload(Agent.app))
            .filter(Agent.agent_id == agent_id)
            .first()
        )
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if agent.marketplace_visibility == MarketplaceVisibility.UNPUBLISHED:
            raise ValueError("Agent is not published to the marketplace")

        # Access check for private agents
        if agent.marketplace_visibility == MarketplaceVisibility.PRIVATE:
            user_app_ids = MarketplaceService._get_user_app_ids(db, user_id)
            if agent.app_id not in user_app_ids:
                raise ValueError("You do not have access to this agent")

        # Generate session ID
        conversation_uuid = str(uuid.uuid4())
        session_id = f"conv_{agent_id}_{conversation_uuid}"

        if not title:
            title = f"Conversación {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')}"

        conversation = Conversation(
            agent_id=agent_id,
            user_id=user_id,
            session_id=session_id,
            title=title,
            source=ConversationSource.MARKETPLACE,
            message_count=0,
        )

        db.add(conversation)
        db.commit()
        db.refresh(conversation)

        logger.info(
            f"Created marketplace conversation {conversation.conversation_id} "
            f"for agent {agent_id}, user {user_id}"
        )
        return conversation
