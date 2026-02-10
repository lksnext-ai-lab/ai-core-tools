from typing import List, Optional
from langchain_core.tools import tool
from models.agent import AgentSkill
from utils.logger import get_logger

logger = get_logger(__name__)


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

    skills_info = []
    for assoc in skill_associations:
        if assoc.skill:
            skill = assoc.skill
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
    # Build a map of normalized skill names to Skill objects
    skill_map = {}
    for assoc in skill_associations:
        if not assoc.skill:
            continue
        skill = assoc.skill
        normalized_name = skill.name.lower().strip()
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

    if not skill_map:
        logger.info("No skills available for this agent")
        return None

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
        skill_key = skill_name.lower().strip()

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
