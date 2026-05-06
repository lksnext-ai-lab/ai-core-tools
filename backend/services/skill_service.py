import hashlib
import io
import json
import re
import zipfile
from typing import Optional, List

from models.skill import Skill, SkillFile
from repositories.skill_repository import SkillRepository
from sqlalchemy.orm import Session
from datetime import datetime
from schemas.skill_schemas import (
    SkillListItemSchema,
    SkillDetailSchema,
    CreateUpdateSkillSchema,
    SkillFileSchema,
)
from utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_field(value) -> list | dict | None:
    """Return a Python object from a JSON text column, or None."""
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def _to_json_text(value) -> Optional[str]:
    """Serialize a list/dict to a JSON string for storage, or None."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _skill_to_detail(skill: Skill) -> SkillDetailSchema:
    files = [
        SkillFileSchema(
            file_id=sf.file_id,
            path=sf.path,
            media_type=sf.media_type,
            content_text=sf.content_text,
            checksum_sha256=sf.checksum_sha256,
        )
        for sf in (skill.files or [])
    ]
    return SkillDetailSchema(
        skill_id=skill.skill_id,
        name=skill.name,
        display_name=skill.display_name,
        description=skill.description or "",
        content=skill.content or "",
        dependencies=_parse_json_field(skill.dependencies),
        allowed_tools=_parse_json_field(skill.allowed_tools),
        runtime=skill.runtime,
        bootstrap_script_path=skill.bootstrap_script_path,
        runtime_options=_parse_json_field(skill.runtime_options),
        is_builtin=skill.is_builtin,
        files=files,
        created_at=skill.create_date,
        is_frozen=skill.is_frozen,
    )


class SkillService:
    @staticmethod
    def list_skills(db: Session, app_id: int) -> List[SkillListItemSchema]:
        """Get all skills visible to an app (owned + builtins) as list items."""
        skills = SkillRepository.get_all_by_app_id(db, app_id)
        return [
            SkillListItemSchema(
                skill_id=skill.skill_id,
                name=skill.name,
                display_name=skill.display_name,
                description=skill.description or "",
                runtime=skill.runtime,
                is_builtin=skill.is_builtin,
                created_at=skill.create_date,
                is_frozen=skill.is_frozen,
            )
            for skill in skills
        ]

    @staticmethod
    def get_skill_detail(db: Session, app_id: int, skill_id: int) -> Optional[SkillDetailSchema]:
        """Get detailed information about a specific skill."""
        if skill_id == 0:
            return SkillDetailSchema(
                skill_id=0,
                name="",
                description="",
                content="",
                created_at=None,
            )

        skill = SkillRepository.get_by_id_and_app_id(db, skill_id, app_id)
        if not skill:
            return None

        return _skill_to_detail(skill)

    @staticmethod
    def create_or_update_skill(
        db: Session,
        app_id: int,
        skill_id: int,
        skill_data: CreateUpdateSkillSchema,
    ) -> Optional[Skill]:
        """Create a new skill or update an existing one."""
        if skill_id == 0:
            from services.tier_enforcement_service import TierEnforcementService
            TierEnforcementService.check_resource_limit(db, app_id, 'skills')

            skill = Skill()
            skill.app_id = app_id
            skill.create_date = datetime.now()
        else:
            skill = db.query(Skill).filter(
                Skill.skill_id == skill_id,
                Skill.app_id == app_id,  # Strict: only owned skills may be edited
            ).first()
            if not skill:
                return None

        skill.name = skill_data.name
        skill.display_name = skill_data.display_name
        skill.description = skill_data.description
        skill.content = skill_data.content
        skill.dependencies = _to_json_text(skill_data.dependencies)
        skill.allowed_tools = _to_json_text(skill_data.allowed_tools)
        skill.runtime = skill_data.runtime
        skill.bootstrap_script_path = skill_data.bootstrap_script_path
        skill.runtime_options = _to_json_text(skill_data.runtime_options)

        if skill_id == 0:
            skill = SkillRepository.create(db, skill)
        else:
            skill = SkillRepository.update(db, skill)

        # Sync inline SkillFile records when provided in the request
        if skill_data.files is not None:
            SkillRepository.delete_skill_files(db, skill.skill_id)
            for file_schema in skill_data.files:
                raw = file_schema.content_text.encode() if file_schema.content_text else b""
                checksum = file_schema.checksum_sha256 or _sha256_hex(raw)
                SkillRepository.upsert_skill_file(
                    db,
                    skill_id=skill.skill_id,
                    path=file_schema.path,
                    media_type=file_schema.media_type,
                    content_text=file_schema.content_text,
                    content_bytes=None,
                    checksum_sha256=checksum,
                )
            db.refresh(skill)

        return skill

    @staticmethod
    def delete_skill(db: Session, app_id: int, skill_id: int) -> bool:
        """Delete a skill (only app-owned skills; builtins cannot be deleted)."""
        return SkillRepository.delete_by_id_and_app_id(db, skill_id, app_id)

    # ------------------------------------------------------------------
    # Import / Export (IT-3)
    # ------------------------------------------------------------------

    @staticmethod
    def export_skill_zip(db: Session, app_id: int, skill_id: int) -> Optional[bytes]:
        """Export a skill as a ZIP archive with SKILL.md and supporting files.

        The archive layout:
            SKILL.md                 — YAML frontmatter + markdown content
            files/<path>             — each SkillFile entry

        Returns:
            ZIP bytes, or None if the skill is not found.
        """
        skill = SkillRepository.get_by_id_and_app_id(db, skill_id, app_id)
        if not skill:
            return None

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            # --- SKILL.md ---
            skill_md = _build_skill_md(skill)
            zf.writestr("SKILL.md", skill_md)

            # --- Supporting files ---
            for sf in (skill.files or []):
                arc_path = f"files/{sf.path.lstrip('/')}"
                if sf.content_bytes is not None:
                    zf.writestr(arc_path, sf.content_bytes)
                elif sf.content_text is not None:
                    zf.writestr(arc_path, sf.content_text.encode())

        return buf.getvalue()

    @staticmethod
    def import_skill_zip(db: Session, app_id: int, zip_bytes: bytes) -> Skill:
        """Import a skill from a ZIP archive produced by ``export_skill_zip``.

        If a skill with the same name already exists in the app, it is
        overwritten.  Built-in skills are never overwritten.

        Args:
            db:        Database session.
            app_id:    Target app.
            zip_bytes: Raw ZIP bytes from the uploaded file.

        Returns:
            The created or updated Skill.

        Raises:
            ValueError: If SKILL.md is missing or malformed.
        """
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            if "SKILL.md" not in names:
                raise ValueError("Invalid skill package: SKILL.md not found.")

            skill_md = zf.read("SKILL.md").decode("utf-8")
            skill_data = _parse_skill_md(skill_md)

            # Find existing app-owned skill by name (builtins are excluded)
            existing = db.query(Skill).filter(
                Skill.app_id == app_id,
                Skill.name == skill_data["name"],
            ).first()

            if existing:
                skill = existing
            else:
                from services.tier_enforcement_service import TierEnforcementService
                TierEnforcementService.check_resource_limit(db, app_id, 'skills')
                skill = Skill()
                skill.app_id = app_id
                skill.create_date = datetime.now()

            skill.name = skill_data["name"]
            skill.display_name = skill_data.get("display_name")
            skill.description = skill_data.get("description", "")
            skill.content = skill_data.get("content", "")
            skill.dependencies = _to_json_text(skill_data.get("dependencies"))
            skill.allowed_tools = _to_json_text(skill_data.get("allowed_tools"))
            skill.runtime = skill_data.get("runtime")
            skill.bootstrap_script_path = skill_data.get("bootstrap_script_path")
            skill.runtime_options = _to_json_text(skill_data.get("runtime_options"))

            if existing:
                skill = SkillRepository.update(db, skill)
            else:
                skill = SkillRepository.create(db, skill)

            # Replace SkillFiles
            SkillRepository.delete_skill_files(db, skill.skill_id)
            for arc_path in names:
                if not arc_path.startswith("files/"):
                    continue
                rel_path = arc_path[len("files/"):]
                if not rel_path:
                    continue
                raw = zf.read(arc_path)
                media_type = _guess_media_type(rel_path)
                try:
                    content_text = raw.decode("utf-8")
                    content_bytes = None
                except UnicodeDecodeError:
                    content_text = None
                    content_bytes = raw
                SkillRepository.upsert_skill_file(
                    db,
                    skill_id=skill.skill_id,
                    path=rel_path,
                    media_type=media_type,
                    content_text=content_text,
                    content_bytes=content_bytes,
                    checksum_sha256=_sha256_hex(raw),
                )

            db.refresh(skill)
            return skill


# ---------------------------------------------------------------------------
# SKILL.md helpers
# ---------------------------------------------------------------------------

def _build_skill_md(skill: Skill) -> str:
    """Serialize a Skill to a SKILL.md string (YAML frontmatter + body)."""
    fm_lines = [f"name: {skill.name}"]
    if skill.display_name:
        fm_lines.append(f"display_name: {skill.display_name}")
    if skill.description:
        fm_lines.append(f"description: >-")
        for line in skill.description.splitlines():
            fm_lines.append(f"  {line}")
    if skill.runtime:
        fm_lines.append(f"runtime: {skill.runtime}")
    deps = _parse_json_field(skill.dependencies)
    if deps:
        fm_lines.append("dependencies:")
        for dep in deps:
            fm_lines.append(f"  - {dep}")
    tools = _parse_json_field(skill.allowed_tools)
    if tools:
        fm_lines.append("allowed-tools:")
        for t in tools:
            fm_lines.append(f"  - {t}")
    if skill.bootstrap_script_path:
        fm_lines.append(f"bootstrap_script_path: {skill.bootstrap_script_path}")
    frontmatter = "\n".join(fm_lines)
    return f"---\n{frontmatter}\n---\n\n{skill.content or ''}"


def _parse_skill_md(text: str) -> dict:
    """Parse a SKILL.md string into a dict with name, description, content, etc."""
    try:
        import yaml  # PyYAML — available in backend requirements
    except ImportError:
        yaml = None  # type: ignore

    frontmatter = {}
    content = text

    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
    if fm_match:
        fm_text, content = fm_match.group(1), fm_match.group(2).lstrip("\n")
        if yaml is not None:
            try:
                frontmatter = yaml.safe_load(fm_text) or {}
            except Exception:
                pass
        else:
            # Minimal key: value parser (no YAML dependency fallback)
            for line in fm_text.splitlines():
                if ":" in line and not line.startswith(" "):
                    k, _, v = line.partition(":")
                    frontmatter[k.strip()] = v.strip()

    name = str(frontmatter.get("name", "")).strip()
    if not name:
        raise ValueError("SKILL.md frontmatter must include a 'name' field.")

    return {
        "name": name,
        "display_name": frontmatter.get("display_name"),
        "description": str(frontmatter.get("description", "")).strip(),
        "content": content,
        "runtime": frontmatter.get("runtime"),
        "dependencies": frontmatter.get("dependencies"),
        "allowed_tools": frontmatter.get("allowed-tools") or frontmatter.get("allowed_tools"),
        "bootstrap_script_path": frontmatter.get("bootstrap_script_path"),
        "runtime_options": frontmatter.get("runtime_options"),
    }


def _guess_media_type(path: str) -> Optional[str]:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return {
        "py": "text/x-python",
        "md": "text/markdown",
        "txt": "text/plain",
        "json": "application/json",
        "yaml": "text/yaml",
        "yml": "text/yaml",
        "html": "text/html",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }.get(ext)

