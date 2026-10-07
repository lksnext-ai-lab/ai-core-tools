"""The agent snapshot DTO consumed by card building, visibility and the executor bridge (step_011).

`A2AAgentSnapshot` is the single, frozen read model built from one eager-loaded
repository call (`repositories.a2a_agent_repository`). Everything downstream of
resolution -- the card builder (`card_service.py`), the catalog, the request
context builder (`context_builders.py`, step_012) and the input pipeline
(`input_service.py`, step_014) -- reads only this DTO, never the ORM rows
directly, so a single query produces everything a request needs and no later
code path triggers a lazy load or a second round trip.

`input_service.py`'s `_AgentSnapshotLike` Protocol only requires `agent_id`,
`app_max_file_size_mb` and `has_memory`; this concrete dataclass satisfies it
structurally (duck typing), no inheritance needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Tuple

from schemas.agent_schemas import clean_a2a_text

if TYPE_CHECKING:
    from models.agent import Agent

# Caps applied when sanitizing Agent.name/description and skill name/description
# for the card (review round 2, LOW-4). These are not the A2A override caps
# (`schemas.agent_schemas`'s `_A2A_*_MAX_LEN`, which Pydantic already enforces
# on write for `a2a_name_override`/`a2a_description_override`) -- Agent.name/
# description and Skill.name/description are never validated by that mixin,
# so a card built from legacy/imported data could otherwise be unbounded or
# carry control characters.
_NAME_MAX_LEN = 255
_DESCRIPTION_MAX_LEN = 1000


@dataclass(frozen=True)
class A2AAgentSnapshot:
    """Everything the A2A surface needs about one agent, resolved once per request.

    Built by `repositories.a2a_agent_repository.get_agent_for_app`/
    `list_enabled_agents_for_app` from a single eager-loaded query. Never
    carries secrets, prompts, silo/tool/MCP identifiers or anything else the
    public or extended card must not leak (FR-5, FR-8, AC-2).
    """

    app_id: int
    app_slug: str
    app_frozen: bool
    app_max_file_size_mb: Optional[int]
    app_name: str

    agent_id: int
    agent_name: str
    agent_description: str
    agent_frozen: bool
    a2a_enabled: bool
    visibility: str  # "public" | "api_key" (Agent.a2a_card_visibility)
    name_override: Optional[str]
    description_override: Optional[str]
    skill_tags: Tuple[str, ...] = field(default_factory=tuple)
    examples: Tuple[str, ...] = field(default_factory=tuple)

    # (skill_id, name, description) — description falls back to the Skill's own
    # description when the AgentSkill association description is unset (FR-6).
    skills: Tuple[Tuple[int, str, str], ...] = field(default_factory=tuple)

    has_output_parser: bool = False
    can_produce_files: bool = False
    accepts_files: bool = True

    ai_provider: Optional[str] = None
    model_id: Optional[str] = None
    has_memory: bool = False

    @property
    def card_name(self) -> str:
        """The name shown on the card: override, else the agent's own name (FR-5)."""
        return self.name_override or self.agent_name or ""

    @property
    def card_description(self) -> str:
        """The description shown on the card: override, else the agent's own description (FR-5)."""
        return self.description_override or self.agent_description or ""


def _safe_clean_text(
    value: Optional[str], *, max_len: int, allow_newline: bool = False, allow_tab: bool = False
) -> str:
    """Best-effort `clean_a2a_text`, char by char, capped to `max_len` (LOW-4).

    `Agent.name`/`Agent.description` and `Skill.name`/`Skill.description` are
    free text with no `clean_a2a_text` validation on write (unlike the A2A
    override fields, which Pydantic already cleans) -- legacy or imported
    rows may carry control/format characters or be unbounded. Building a
    snapshot must never raise on that data, so disallowed characters are
    dropped individually (via the real validator, one character at a time)
    rather than rejecting the whole string.
    """
    if not value:
        return ""
    stripped = value.strip()
    kept_chars = []
    for ch in stripped:
        try:
            clean_a2a_text(ch, allow_newline=allow_newline, allow_tab=allow_tab)
        except ValueError:
            continue
        kept_chars.append(ch)
    return "".join(kept_chars)[:max_len]


def build_snapshot(agent: "Agent") -> A2AAgentSnapshot:
    """Build an `A2AAgentSnapshot` from one eager-loaded `Agent` row.

    Call only on an `Agent` fetched through
    `repositories.a2a_agent_repository.get_agent_for_app`/
    `list_enabled_agents_for_app` -- both eager-load `app`, `ai_service`,
    `output_parser` and `skill_associations.skill`, so this function never
    triggers a lazy load.

    `can_produce_files` is true when the agent can run the code interpreter
    or has the provider-side `image_generation` server tool enabled (FR-7).
    `accepts_files` is always true: the existing chat file pipeline
    (`FileManagementService.resolve_chat_files`) does not reject attachments
    based on agent type.

    `visibility` defaults to `"api_key"` -- not `"public"` -- for any value
    other than the exact string `"public"` (including `None`/empty, which
    should not occur given the DB's `NOT NULL`+`CHECK` constraint, but a
    snapshot builder must fail closed rather than assume the safe case;
    review round 2, LOW-3). `visibility_service`/`card_service` mirror this
    by gating on `!= "public"` rather than `== "api_key"`.
    """
    app = agent.app
    skills = tuple(
        (
            assoc.skill_id,
            _safe_clean_text(assoc.skill.name if assoc.skill else "", max_len=_NAME_MAX_LEN),
            _safe_clean_text(
                assoc.description or (assoc.skill.description if assoc.skill else "") or "",
                max_len=_DESCRIPTION_MAX_LEN,
                allow_newline=True,
                allow_tab=True,
            ),
        )
        for assoc in (agent.skill_associations or [])
        if assoc.skill is not None
    )
    server_tools = agent.server_tools or []
    can_produce_files = bool(agent.enable_code_interpreter) or "image_generation" in server_tools
    visibility = agent.a2a_card_visibility if agent.a2a_card_visibility == "public" else "api_key"

    return A2AAgentSnapshot(
        app_id=agent.app_id,
        app_slug=app.slug if app else "",
        app_frozen=bool(app.is_frozen) if app else False,
        app_max_file_size_mb=app.max_file_size_mb if app else None,
        app_name=app.name if app else "",
        agent_id=agent.agent_id,
        agent_name=_safe_clean_text(agent.name, max_len=_NAME_MAX_LEN),
        agent_description=_safe_clean_text(
            agent.description, max_len=_DESCRIPTION_MAX_LEN, allow_newline=True, allow_tab=True
        ),
        agent_frozen=bool(agent.is_frozen),
        a2a_enabled=bool(agent.a2a_enabled),
        visibility=visibility,
        name_override=agent.a2a_name_override,
        description_override=agent.a2a_description_override,
        skill_tags=tuple(agent.a2a_skill_tags or []),
        examples=tuple(agent.a2a_examples or []),
        skills=skills,
        has_output_parser=agent.output_parser_id is not None,
        can_produce_files=can_produce_files,
        accepts_files=True,
        ai_provider=agent.ai_service.provider if agent.ai_service else None,
        model_id=agent.ai_service.description if agent.ai_service else None,
        has_memory=bool(agent.has_memory),
    )


__all__ = ["A2AAgentSnapshot", "build_snapshot"]
