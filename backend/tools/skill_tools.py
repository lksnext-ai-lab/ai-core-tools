import posixpath
from typing import List, Optional, Any
from langchain_core.tools import tool
from models.agent import AgentSkill
from utils.logger import get_logger

logger = get_logger(__name__)


def _build_skill_map(skill_associations: List[AgentSkill]) -> dict[str, Any]:
    """Return skill objects keyed by normalized skill name."""
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
    return skill_map


def _available_skills_text(skill_map: dict[str, Any]) -> str:
    return ", ".join(sorted({skill.name for skill in skill_map.values()}))


def _normalize_skill_file_path(path: str, skill_name: str) -> str:
    """Normalize a package-root-relative SkillFile path.

    The model may pass the path exactly as referenced in SKILL.md
    (``pptxgenjs.md``), or as the sandbox path returned by ``load_skill``
    (``/workspace/.skills/pptx/pptxgenjs.md``). Store and compare paths using
    the package-root-relative representation.
    """
    raw_path = (path or "").strip().replace("\\", "/")
    if not raw_path:
        raise ValueError("path must not be empty")

    skill_prefix = skill_name.lower().strip()
    normalized_lower = raw_path.lower()
    for prefix in (
        f"/workspace/.skills/{skill_prefix}/",
        f"workspace/.skills/{skill_prefix}/",
        f".skills/{skill_prefix}/",
    ):
        if normalized_lower.startswith(prefix):
            raw_path = raw_path[len(prefix):]
            break

    while raw_path.startswith("./"):
        raw_path = raw_path[2:]

    if raw_path.startswith("/"):
        raise ValueError("path must be relative to the skill package")

    normalized = posixpath.normpath(raw_path)
    if normalized in ("", ".") or normalized.startswith("../") or normalized == "..":
        raise ValueError("path must not escape the skill package")
    return normalized


def _decode_skill_file_content(skill_file: Any) -> str:
    content_text = getattr(skill_file, "content_text", None)
    if content_text is not None:
        return content_text

    content_bytes = getattr(skill_file, "content_bytes", None)
    if content_bytes is None:
        return ""

    try:
        return content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        path = getattr(skill_file, "path", "file")
        media_type = getattr(skill_file, "media_type", None) or "application/octet-stream"
        return (
            f"[BINARY SKILL FILE: {path}]\n"
            f"Media type: {media_type}\n"
            f"Size: {len(content_bytes)} bytes\n"
            "This file is binary and cannot be returned as text through this tool."
        )


# ---------------------------------------------------------------------------
# Idempotency helper (step 4.7)
# ---------------------------------------------------------------------------

def _is_loaded(handle: Any, skill: Any) -> bool:
    """Return True if *skill* is already activated for the sandbox in *handle*.

    Checks ``handle.active_skills`` keyed by skill name; the stored entry must
    reference the current ``handle.sandbox_id`` and have both phases completed
    successfully (files=ok, bootstrap=ok or skipped).
    """
    existing = handle.active_skills.get(skill.name)
    if not existing:
        return False
    if existing.get("sandbox_id") != handle.sandbox_id:
        return False
    phases = existing.get("phases", {})
    return (
        phases.get("files") == "ok"
        and phases.get("bootstrap") in ("ok", "skipped")
    )


def _get_cached_instruction(skill: Any) -> str:
    """Return the cached activation text for an already-loaded skill."""
    return (
        f"[SKILL ALREADY ACTIVE: {skill.name}]\n\n"
        "This skill is already loaded. Proceed directly with the task."
    )


# ---------------------------------------------------------------------------
# Core load_skill logic (standalone, testable) — step 4.7 / 4.8 / 4.9
# ---------------------------------------------------------------------------

def load_skill(skill: Any, handle: Any, provider: Any) -> str:
    """Activate a skill in the sandbox and return the instruction text.

    This standalone function contains the core skill-loading logic and is
    intended to be called both from the LangChain tool wrapper and directly
    in tests.

    Args:
        skill:    Skill ORM object (or SimpleNamespace/mock in tests).
        handle:   Active :class:`~tools.sandbox.provider.SandboxHandle`
                  (may be ``None`` when the sandbox is disabled).
        provider: :class:`~tools.sandbox.provider.SandboxProvider` instance
                  (may be ``None`` when the sandbox is disabled).

    Returns:
        Activation text to return to the LLM.
    """
    # --- Idempotency: use handle.active_skills (survives turn boundaries) ---
    if handle is not None and _is_loaded(handle, skill):
        logger.info("Skill already loaded (skipping re-initialization): %s", skill.name)
        return _get_cached_instruction(skill)

    logger.info("Loading skill: %s", skill.name)

    # --- Content-presence check replaces runtime field (step 4.8) ---
    has_package = bool(getattr(skill, "files", None)) or bool(
        getattr(skill, "bootstrap_script_path", None)
    )
    phase_status: dict = {"phases": {}}

    if has_package and handle is not None and provider is not None:
        try:
            phase_status = provider.ensure_skill(handle, skill)
            phases = phase_status.get("phases", {})
            failed_phases = {
                phase: status
                for phase, status in phases.items()
                if isinstance(status, str) and status.startswith("failed:")
            }
            if failed_phases:
                logger.warning(
                    "Sandbox environment preparation failed for skill %s: %s",
                    skill.name,
                    failed_phases,
                )
            else:
                logger.info("Sandbox environment prepared for skill: %s", skill.name)
        except Exception as exc:
            logger.error(
                "Error preparing sandbox for skill %s: %s", skill.name, exc, exc_info=True
            )
            phase_status = {"phases": {"files": f"failed: {exc}", "bootstrap": "skipped"}}

    # --- Surface phase status (step 4.9) ---
    phases = phase_status.get("phases", {})
    files_status = phases.get("files", "ok")   # default ok when no package
    bootstrap_status = phases.get("bootstrap", "skipped")

    if isinstance(files_status, str) and files_status.startswith("failed:"):
        # Hard failure — do NOT mark as loaded
        return (
            f"[SKILL ACTIVATION FAILED: {skill.name}]\n\n"
            f"File extraction failed: {files_status}.\n"
            "The skill cannot be used in this turn. "
            "You may retry by calling this tool again or inform the user."
        )

    # Mark as loaded in handle.active_skills for cross-turn idempotency (step 4.7)
    if handle is not None:
        handle.active_skills[skill.name] = {
            "sandbox_id": handle.sandbox_id,
            "phases": {"files": files_status, "bootstrap": bootstrap_status},
        }

    preamble = f"[SKILL ACTIVATED: {skill.name}]\n\n"
    files_dir = phase_status.get("files_dir")
    if files_dir:
        preamble += (
            f"Supporting files are available in `{files_dir}`. "
            "When the instructions reference another local file, read that file "
            "from this directory before choosing an implementation path.\n"
        )

    if isinstance(bootstrap_status, str) and bootstrap_status.startswith("failed:"):
        preamble += (
            f"Runtime status: files={files_status}, bootstrap={bootstrap_status}.\n"
            "Use the instructions below, but treat runtime setup as incomplete. "
            "If the preferred implementation depends on a missing tool or package, "
            "retry or repair setup before falling back.\n"
        )

    preamble += "\n"

    return preamble + (getattr(skill, "content", "") or "")


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def _is_skill_healthy_in_handle(handle: Any, skill_name: str) -> bool:
    """Return True if *skill_name* is already active and healthy in *handle*.

    A skill is considered healthy when its ``files`` phase is ``"ok"`` and its
    ``bootstrap`` phase is either ``"ok"`` or ``"skipped"``.
    """
    existing = handle.active_skills.get(skill_name)
    if not existing:
        return False
    if existing.get("sandbox_id") != getattr(handle, "sandbox_id", None):
        return False
    phases = existing.get("phases", {})
    return (
        phases.get("files") == "ok"
        and phases.get("bootstrap") in ("ok", "skipped")
    )


def generate_skills_system_prompt_section(
    skill_associations: List[AgentSkill],
    *,
    active_skill_names: Optional[set] = None,
    handle: Any = None,
) -> Optional[str]:
    """Generate a system prompt section that informs the agent about available skills.

    When *active_skill_names* is ``None`` (legacy mode), all skills with a
    populated ``skill`` relationship are included.  When a set is provided
    (router mode) only skills whose name appears in *active_skill_names* OR
    that are already active and healthy in *handle* are included, ensuring the
    LLM retains awareness of skills it has already loaded during the session.

    Args:
        skill_associations: List of AgentSkill associations.
        active_skill_names: Optional set of skill names selected by the router.
            Pass ``None`` for legacy (include-all) behaviour.
        handle: Optional sandbox handle; used to check ``handle.active_skills``
            so already-active skills are always shown even if not router-selected.

    Returns:
        A formatted string to append to the system prompt, or None if no skills
        should be shown.
    """
    if not skill_associations:
        return None

    if active_skill_names is None:
        # Legacy behaviour: include every skill that has a relationship object.
        visible_assocs = [a for a in skill_associations if a.skill]
    else:
        selected_names = {
            str(name).lower().strip()
            for name in active_skill_names
            if name is not None
        }
        visible_assocs = []
        for assoc in skill_associations:
            if not assoc.skill:
                continue
            skill_name = assoc.skill.name
            if skill_name.lower().strip() in selected_names:
                visible_assocs.append(assoc)
            elif (
                handle is not None
                and _is_skill_healthy_in_handle(handle, skill_name)
            ):
                visible_assocs.append(assoc)

    if not visible_assocs:
        return None

    skills_info = []
    for assoc in visible_assocs:
        skill = assoc.skill
        description = skill.description or "No description available"
        skills_info.append(f"  - **{skill.name}**: {description}")

    skills_list = "\n".join(skills_info)

    return f"""
<available_skills>
You have access to the following specialized skills that you can load on-demand using the `load_skill` tool:

{skills_list}

When a user's request matches one of these skills, use the `load_skill` tool with the skill name to load detailed instructions for that specific task. If the returned instructions reference another file such as `pptxgenjs.md`, `editing.md`, a script, or any other supporting file, use the `read_skill_file` tool to retrieve that file before choosing an implementation path. Skills with supporting package files will also automatically prepare the sandbox environment and copy those files under `/workspace/.skills/<skill-name>`. After loading a skill, follow the returned instructions and use the REPL language or shell commands the skill calls for; do not default to Python when the skill directs you to another runtime. Only load a skill when it's relevant to the current task.
</available_skills>"""


def create_skill_loader_tool(
    skill_associations: List[AgentSkill],
    sandbox_handle: Any = None,
    sandbox_provider: Any = None,
):
    """
    Create a load_skill LangChain tool that allows agents to dynamically load skill instructions.

    For skills with package files or a bootstrap script, if *sandbox_handle* and
    *sandbox_provider* are supplied the tool will call ``provider.ensure_skill()``
    to copy assets into the sandbox and optionally run the bootstrap script.
    Idempotency is keyed on ``handle.active_skills`` so it survives turn boundaries.

    Args:
        skill_associations: List of AgentSkill associations containing the skills
            available to the agent.
        sandbox_handle: Optional active sandbox handle for runtime skill setup.
        sandbox_provider: Optional sandbox provider used to call ``ensure_skill``.

    Returns:
        A LangChain tool that can load skill instructions by name, or None if no
        skills are available.
    """
    # Build a map of normalized skill names to Skill objects
    skill_map = _build_skill_map(skill_associations)

    if not skill_map:
        logger.info("No skills available for this agent")
        return None

    available_skills = _available_skills_text(skill_map)
    logger.info("Creating skill loader tool with %d skills: %s", len(skill_map), available_skills)

    @tool
    def load_skill_tool(skill_name: str) -> str:
        """Activate or retry activation of an attached Skill that has supporting package files
        or a bootstrap script. This copies Skill files into the sandbox workspace and runs
        the bootstrap script if configured. Does not install external dependencies.

        Use this tool when you need to activate specialized behavior or follow specific guidelines.
        The skill will provide detailed instructions on how to handle certain tasks.

        This tool is idempotent: calling it again for an already-loaded skill returns the cached
        instructions without repeating sandbox initialization.

        Args:
            skill_name: The name of the skill to load (case-insensitive)

        Returns:
            The skill instructions in markdown format, with an activation status preamble.
        """
        skill_key = skill_name.lower().strip()

        if skill_key not in skill_map:
            return f"Skill '{skill_name}' not found. Available skills: {available_skills}"

        skill = skill_map[skill_key]
        return load_skill(skill, sandbox_handle, sandbox_provider)

    return load_skill_tool


def create_skill_file_reader_tool(skill_associations: List[AgentSkill]):
    """
    Create a read_skill_file LangChain tool for retrieving SkillFile contents.

    This complements ``load_skill``: the loader returns the main SKILL.md body,
    while this tool lets the model fetch supporting files referenced by those
    instructions without needing to know where the package lives in the sandbox.
    """
    skill_map = _build_skill_map(skill_associations)
    if not skill_map:
        logger.info("No skills available for skill file reader tool")
        return None

    available_skills = _available_skills_text(skill_map)
    logger.info(
        "Creating skill file reader tool with %d skills: %s",
        len(skill_map),
        available_skills,
    )

    @tool("read_skill_file")
    def read_skill_file_tool(skill_name: str, path: str) -> str:
        """Read a supporting file bundled with an attached Skill.

        Use this after ``load_skill`` when the skill instructions reference
        files such as ``pptxgenjs.md``, ``editing.md``, scripts, templates, or
        other package resources. The path may be package-relative or the full
        sandbox path under ``/workspace/.skills/<skill-name>/``.

        Args:
            skill_name: The name of the skill whose file should be read.
            path: The referenced file path.

        Returns:
            Text content for the requested file, or a clear error/listing when
            the skill or path is not available.
        """
        skill_key = skill_name.lower().strip()
        if skill_key not in skill_map:
            return f"Skill '{skill_name}' not found. Available skills: {available_skills}"

        skill = skill_map[skill_key]
        files = list(getattr(skill, "files", None) or [])
        if not files:
            return f"Skill '{skill.name}' has no supporting files."

        try:
            normalized_path = _normalize_skill_file_path(path, skill.name)
        except ValueError as exc:
            return f"Invalid skill file path '{path}': {exc}"

        file_map = {getattr(file, "path", ""): file for file in files}
        skill_file = file_map.get(normalized_path)
        if skill_file is None:
            available_files = ", ".join(sorted(p for p in file_map if p)) or "(none)"
            return (
                f"Skill file '{normalized_path}' not found for skill '{skill.name}'. "
                f"Available files: {available_files}"
            )

        content = _decode_skill_file_content(skill_file)
        return (
            f"[SKILL FILE: {skill.name}/{normalized_path}]\n\n"
            f"{content}"
        )

    return read_skill_file_tool
