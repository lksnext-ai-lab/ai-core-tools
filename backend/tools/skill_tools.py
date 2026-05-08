from typing import List, Optional, Any
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
            runtime_badge = " *(runtime)*" if getattr(skill, "runtime", None) == "python-sandbox" else ""
            skills_info.append(f"  - **{skill.name}**{runtime_badge}: {description}")

    if not skills_info:
        return None

    skills_list = "\n".join(skills_info)

    return f"""
<available_skills>
You have access to the following specialized skills that you can load on-demand using the `load_skill` tool:

{skills_list}

When a user's request matches one of these skills, use the `load_skill` tool with the skill name to load detailed instructions for that specific task. Skills marked *(runtime)* will also automatically prepare the sandbox environment so you can call `python_repl` immediately afterwards. Only load a skill when it's relevant to the current task.
</available_skills>"""


def create_skill_loader_tool(
    skill_associations: List[AgentSkill],
    sandbox_handle: Any = None,
    sandbox_provider: Any = None,
):
    """
    Create a load_skill tool that allows agents to dynamically load skill instructions.

    For skills with ``runtime == "python-sandbox"``, if *sandbox_handle* and
    *sandbox_provider* are supplied the tool will also call
    ``provider.ensure_skill()`` to install dependencies and copy assets into the
    sandbox.  Subsequent calls for the same skill are idempotent — the sandbox
    setup runs only once per tool instance (per conversation turn sequence).

    Args:
        skill_associations: List of AgentSkill associations containing the skills available to the agent
        sandbox_handle: Optional active sandbox handle for runtime skill setup
        sandbox_provider: Optional sandbox provider used to call ``ensure_skill``

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

    # Track which skills have already been fully loaded (instructions + sandbox)
    # within this tool instance to avoid redundant sandbox re-initialization.
    _loaded_skills: set = set()

    @tool
    def load_skill(skill_name: str) -> str:
        """Load specialized instructions for a skill and, when the skill requires
        Python execution, automatically prepare the sandbox environment.

        Use this tool when you need to activate specialized behavior or follow specific guidelines.
        The skill will provide detailed instructions on how to handle certain tasks.

        For skills that require Python execution (runtime-capable skills marked with
        ``runtime == 'python-sandbox'``), calling this tool is **sufficient** to have the
        sandbox fully ready — dependencies are installed and assets copied automatically.
        You can invoke ``python_repl`` immediately after without any additional setup step.

        This tool is idempotent: calling it again for the same skill returns the cached
        instructions without repeating the sandbox initialization.

        Args:
            skill_name: The name of the skill to load (case-insensitive)

        Returns:
            The skill instructions in markdown format.
        """
        skill_key = skill_name.lower().strip()

        # Idempotency — return early if already loaded in this session
        if skill_key in _loaded_skills:
            skill = skill_map.get(skill_key)
            display_name = skill.name if skill else skill_name
            logger.info(f"Skill already loaded (skipping re-initialization): {display_name}")
            return (
                f"[SKILL ALREADY ACTIVE: {display_name}]\n\n"
                "This skill is already loaded. Proceed directly with the task."
            )

        if skill_key not in skill_map:
            return f"Skill '{skill_name}' not found. Available skills: {available_skills}"

        skill = skill_map[skill_key]
        logger.info(f"Loading skill: {skill.name}")

        # Best-effort sandbox setup for runtime skills — never surfaces errors to the LLM
        is_runtime = getattr(skill, "runtime", None) == "python-sandbox"
        if is_runtime and sandbox_handle is not None and sandbox_provider is not None:
            try:
                sandbox_provider.ensure_skill(sandbox_handle, skill)
                logger.info(f"Sandbox environment prepared for skill: {skill.name}")
            except Exception as e:
                logger.error(
                    "Error preparing sandbox for skill %s: %s", skill.name, e, exc_info=True
                )

        _loaded_skills.add(skill_key)

        # Return the skill content with a clear activation header
        return f"""[SKILL ACTIVATED: {skill.name}]

{skill.content}

---
Follow the above instructions carefully for the current task."""

    return load_skill
