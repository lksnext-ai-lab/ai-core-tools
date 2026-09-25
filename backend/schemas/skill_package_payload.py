from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class SkillPackagePayload:
    """Detached, ORM-free description of a skill package consumed by sandbox providers (AD-7).

    Built by ``SkillPackageService.build_payload`` before entering a provider; contains no ORM objects and no
    Session. ``files`` holds every package file except SKILL.md as ``(package-relative path, bytes)``.
    ``allowed_tools`` is deliberately absent: it is metadata only and never enforced (AD-15).
    """
    skill_id: int
    name: str
    display_name: Optional[str] = None
    files: Tuple[Tuple[str, bytes], ...] = ()
    bootstrap_script_path: Optional[str] = None
    runtime: Optional[str] = None
    runtime_options: Dict[str, Any] = field(default_factory=dict)
