from typing import Dict, List, Optional
from langchain_core.tools import tool
from models.agent import AgentSkill
from models.skill import Skill
from utils.logger import get_logger
from utils.skill_names import fold_name

logger = get_logger(__name__)


def resolve_agent_skills(skill_associations: List[AgentSkill]) -> List[Skill]:
    """Single source of truth for which skills an agent actually uses this turn.

    This is the AD-13 mitigation: every prompt/tool consumer must go through this
    function instead of iterating ``agent.skill_associations`` directly, so they
    can never drift from each other.

    Drops:
      - associations with no loaded skill (defensive, matches prior behaviour)
      - disabled skills (``is_enabled`` falsy; the P2 disable kill switch, applies
        to both system and app skills)
      - duplicate ``fold_name``-normalised names: on a collision an app skill
        always wins over a same-named system skill (FR-11 "app skill wins"),
        ties broken by ``skill_id``. ``Agent.skill_associations`` has no
        ``ORDER BY``, so relying on DB/iteration order for this precedence
        would let a same-named app/system pair resolve arbitrarily and could
        let an attacker-controlled app skill silently shadow a trusted
        platform skill (or vice versa). A warning is logged for every skill
        dropped to a collision.

    Preserves the original association ordering otherwise.

    Args:
        skill_associations: List of AgentSkill associations

    Returns:
        Ordered list of resolved Skill objects the agent should use this turn
    """
    candidates: List[Skill] = []
    for assoc in skill_associations:
        skill = assoc.skill
        if not skill:
            continue
        if skill.is_enabled is not None and not skill.is_enabled:
            continue
        candidates.append(skill)

    if not candidates:
        return []

    # Resolve the winner of each name collision deterministically: process
    # app skills (app_id is not None) before system skills, ties broken by
    # skill_id, so the winner never depends on association/DB ordering.
    skill_map: Dict[str, Skill] = {}
    for skill in sorted(candidates, key=lambda s: (s.app_id is None, s.skill_id)):
        normalized_name = fold_name(skill.name)
        existing_skill = skill_map.get(normalized_name)
        if existing_skill is not None and existing_skill is not skill:
            logger.warning(
                "Duplicate skill name detected after normalization: '%s'. "
                "Keeping existing skill '%s' and ignoring new skill '%s'.",
                normalized_name,
                getattr(existing_skill, "name", repr(existing_skill)),
                getattr(skill, "name", repr(skill)),
            )
            continue
        skill_map[normalized_name] = skill

    winners = {id(skill) for skill in skill_map.values()}
    # Preserve the original association ordering for everything that survived.
    return [skill for skill in candidates if id(skill) in winners]


def generate_skills_system_prompt_section(skill_associations: List[AgentSkill]) -> Optional[str]:
    """
    Generate a system prompt section that informs the agent about available skills.

    This allows the agent to know upfront what skills are available and decide
    when to load them based on the current task.

    Args:
        skill_associations: List of AgentSkill associations

    Returns:
        A formatted string to append to the system prompt, or None if no skills
    """
    if not skill_associations:
        return None

    skills = resolve_agent_skills(skill_associations)
    if not skills:
        return None

    skills_info = []
    for skill in skills:
        description = skill.description or "No description available"
        skills_info.append(f"  - **{skill.name}**: {description}")

    if not skills_info:
        return None

    skills_list = "\n".join(skills_info)

    return f"""
<available_skills>
You have access to the following specialized skills that you can load on-demand using the `load_skill` tool:

{skills_list}

When a user's request matches one of these skills, use the `load_skill` tool with the skill name to load detailed instructions for that specific task. Only load a skill when it's relevant to the current task.
</available_skills>"""


def create_skill_loader_tool(skill_associations: List[AgentSkill]):
    """
    Create a load_skill tool that allows agents to dynamically load skill instructions.

    Args:
        skill_associations: List of AgentSkill associations containing the skills available to the agent

    Returns:
        A LangChain tool that can load skill instructions by name
    """
    skills = resolve_agent_skills(skill_associations)

    if not skills:
        logger.info("No skills available for this agent")
        return None

    # Build a map of normalized skill names to Skill objects for tool-time lookup
    skill_map: Dict[str, Skill] = {fold_name(skill.name): skill for skill in skills}

    # Use original skill names for display to the user
    available_skills = ", ".join(sorted({skill.name for skill in skill_map.values()}))
    logger.info(f"Creating skill loader tool with {len(skill_map)} skills: {available_skills}")

    @tool
    def load_skill(skill_name: str) -> str:
        """Load specialized instructions for a skill.

        Use this tool when you need to activate specialized behavior or follow specific guidelines.
        The skill will provide detailed instructions on how to handle certain tasks.

        Args:
            skill_name: The name of the skill to load (case-insensitive)

        Returns:
            The skill instructions in markdown format, or an error message if not found
        """
        skill_key = fold_name(skill_name)

        if skill_key not in skill_map:
            return f"Skill '{skill_name}' not found. Available skills: {available_skills}"

        skill = skill_map[skill_key]
        logger.info(f"Loading skill: {skill.name}")

        # Return the skill content with a clear activation header
        return f"""[SKILL ACTIVATED: {skill.name}]

{skill.content}

---
Follow the above instructions carefully for the current task."""

    return load_skill
