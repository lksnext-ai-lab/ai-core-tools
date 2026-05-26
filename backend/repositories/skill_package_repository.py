"""
SkillPackageRepository — import, export, and validation for Agent Skill ZIP packages.

The canonical ZIP layout (v2):
    SKILL.md                    — YAML frontmatter + markdown body at archive root
    scripts/bootstrap.py        — package-root-relative file paths
    references/schema.md
    assets/template.docx

Legacy layout (input only — do NOT produce):
    SKILL.md
    files/scripts/bootstrap.py  — legacy files/ prefix is stripped on import

Multi-skill uploads (input only):
    analytics/SKILL.md
    analytics/scripts/bootstrap.py
    writing/skill.md
    writing/references/style.md
"""
from __future__ import annotations

import hashlib
import io
import posixpath
import zipfile
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Validation limits (hard errors)
# ---------------------------------------------------------------------------
_MAX_TOTAL_BYTES = 50 * 1024 * 1024   # 50 MB total decompressed
_MAX_FILE_COUNT = 500
_MAX_SINGLE_FILE_BYTES = 10 * 1024 * 1024  # 10 MB per file
_MAX_DECOMPRESS_RATIO = 100            # zip-bomb protection

# Known frontmatter keys — unknown extras produce a warning
_KNOWN_FM_KEYS = {
    "name", "display_name", "description", "content", "runtime",
    "dependencies", "allowed-tools", "allowed_tools",
    "bootstrap_script_path", "runtime_options", "when_to_use",
    "disable-model-invocation", "disable_model_invocation",
}


# ---------------------------------------------------------------------------
# Path validator (step 4.4)
# ---------------------------------------------------------------------------

def _validate_skill_file_path(path: str) -> None:
    """
    Raise ValueError if *path* is unsafe for a skill package.

    Rules:
    - Must not be empty.
    - Must not be absolute (start with /).
    - Must not start with '..'.
    - Must not normalize outside the package root (posixpath traversal).
    - Must not have leading/trailing whitespace.
    """
    if not path:
        raise ValueError("SkillFile.path must not be empty.")
    if path != path.strip():
        raise ValueError(
            f"SkillFile.path must not have leading/trailing whitespace: {path!r}"
        )
    if posixpath.isabs(path):
        raise ValueError(f"SkillFile.path must be relative, got: {path!r}")
    normalized = posixpath.normpath(path)
    if normalized.startswith(".."):
        raise ValueError(
            f"SkillFile.path must not escape the package root: {path!r}"
        )


# ---------------------------------------------------------------------------
# Return types
# ---------------------------------------------------------------------------

@dataclass
class SkillPackageValidation:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0


class SkillCatalogItem(dict):
    """TypedDict-like dict with keys: skill_id, name, description, when_to_use,
    disable_model_invocation."""


class SkillActivationPayload(dict):
    """TypedDict-like dict with keys: skill_id, name, body, frontmatter,
    files_dir, file_paths."""


class SkillFileSummary(dict):
    """TypedDict-like dict with keys: path, size_bytes."""


class SkillFileContent(dict):
    """TypedDict-like dict with keys: path, content (bytes), mime_type."""


@dataclass(frozen=True)
class _SkillPackageEntry:
    """One skill package discovered inside an uploaded ZIP."""

    root: str
    skill_md_path: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def _parse_skill_md(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body_text)."""
    import re
    try:
        import yaml
    except ImportError:
        yaml = None  # type: ignore

    fm: dict = {}
    body = text

    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
    if m:
        fm_text, body = m.group(1), m.group(2).lstrip("\n")
        if yaml is not None:
            try:
                fm = yaml.safe_load(fm_text) or {}
            except Exception:
                pass
        else:
            for line in fm_text.splitlines():
                if ":" in line and not line.startswith(" "):
                    k, _, v = line.partition(":")
                    fm[k.strip()] = v.strip()

    return fm, body


def _normalized_archive_path(path: str) -> str:
    """Return a normalized POSIX archive path."""
    return posixpath.normpath(path.replace("\\", "/"))


def _is_skill_md_path(path: str) -> bool:
    return posixpath.basename(path).lower() == "skill.md"


def _discover_skill_entries(zf: zipfile.ZipFile) -> list[_SkillPackageEntry]:
    """Find every archive folder that contains a SKILL.md/skill.md file."""
    entries: list[_SkillPackageEntry] = []
    seen_roots: set[str] = set()

    for info in zf.infolist():
        if info.is_dir():
            continue
        normalized = _normalized_archive_path(info.filename)
        if not _is_skill_md_path(normalized):
            continue
        root = posixpath.dirname(normalized)
        if root in seen_roots:
            continue
        seen_roots.add(root)
        entries.append(_SkillPackageEntry(root=root, skill_md_path=info.filename))

    return sorted(entries, key=lambda entry: (entry.root.count("/"), entry.root))


def _is_descendant(path: str, root: str) -> bool:
    if not root:
        return True
    return path == root or path.startswith(f"{root}/")


def _resource_entries_for_skill(
    zf: zipfile.ZipFile,
    entry: _SkillPackageEntry,
    all_entries: list[_SkillPackageEntry],
) -> list[tuple[str, str]]:
    """Return ``(archive_path, package_relative_path)`` resources for one skill."""
    nested_roots = [
        other.root
        for other in all_entries
        if other.root
        and other.root != entry.root
        and _is_descendant(other.root, entry.root)
    ]
    resources: list[tuple[str, str]] = []

    for info in zf.infolist():
        if info.is_dir():
            continue
        normalized = _normalized_archive_path(info.filename)
        if normalized == _normalized_archive_path(entry.skill_md_path):
            continue
        if not _is_descendant(normalized, entry.root):
            continue
        if any(_is_descendant(normalized, nested_root) for nested_root in nested_roots):
            continue

        rel = normalized[len(entry.root):].lstrip("/") if entry.root else normalized
        # Compatibility: old packages stored resources under files/<path>.
        rel = rel[len("files/"):] if rel.startswith("files/") else rel
        if rel:
            resources.append((info.filename, rel))

    return resources


def _build_skill_md(skill) -> str:
    """Reconstruct a SKILL.md string for export (no dependencies, no runtime)."""
    fm_lines = [f"name: {skill.name}"]
    if skill.display_name:
        fm_lines.append(f"display_name: {skill.display_name}")
    if skill.description:
        fm_lines.append("description: >-")
        for line in skill.description.splitlines():
            fm_lines.append(f"  {line}")

    # dependencies and runtime intentionally omitted in v2 export
    import json

    def _from_json(v):
        if v is None:
            return None
        if isinstance(v, (list, dict)):
            return v
        try:
            return json.loads(v)
        except Exception:
            return None

    tools = _from_json(getattr(skill, "allowed_tools", None))
    if tools:
        fm_lines.append("allowed-tools:")
        for t in tools:
            fm_lines.append(f"  - {t}")
    if skill.bootstrap_script_path:
        fm_lines.append(f"bootstrap_script_path: {skill.bootstrap_script_path}")

    frontmatter = "\n".join(fm_lines)
    return f"---\n{frontmatter}\n---\n\n{skill.content or ''}"


# ---------------------------------------------------------------------------
# Repository class
# ---------------------------------------------------------------------------

class SkillPackageRepository:
    """Import, export, validate, and query Agent Skill ZIP packages."""

    # ------------------------------------------------------------------
    # validate_package
    # ------------------------------------------------------------------

    @staticmethod
    def validate_package(zip_bytes: bytes) -> SkillPackageValidation:
        """Validate a ZIP against hard-error and warning rules."""
        result = SkillPackageValidation()

        # ---- Zip-bomb / size guard (before opening) ------------------
        compressed_size = len(zip_bytes)

        try:
            buf = io.BytesIO(zip_bytes)
            zf = zipfile.ZipFile(buf)
        except zipfile.BadZipFile as exc:
            result.errors.append(f"Cannot open ZIP: {exc}")
            return result

        with zf:
            infos = zf.infolist()

            # File count
            if len(infos) > _MAX_FILE_COUNT:
                result.errors.append(
                    f"Archive exceeds maximum file count ({len(infos)} > {_MAX_FILE_COUNT})."
                )

            # Total / per-file size + decompression ratio
            total_bytes = 0
            for info in infos:
                if info.file_size > _MAX_SINGLE_FILE_BYTES:
                    result.errors.append(
                        f"File '{info.filename}' exceeds maximum size "
                        f"({info.file_size} > {_MAX_SINGLE_FILE_BYTES})."
                    )
                total_bytes += info.file_size
            if total_bytes > _MAX_TOTAL_BYTES:
                result.errors.append(
                    f"Archive total decompressed size exceeds limit "
                    f"({total_bytes} > {_MAX_TOTAL_BYTES})."
                )
            if compressed_size > 0 and total_bytes > compressed_size * _MAX_DECOMPRESS_RATIO:
                result.errors.append(
                    "Archive decompression ratio exceeds limit (possible zip bomb)."
                )

            # Archive-wide path safety checks.
            seen_archive_normalized: set[str] = set()
            for info in infos:
                if info.is_dir():
                    continue
                arc_name = info.filename
                # Absolute
                if posixpath.isabs(arc_name):
                    result.errors.append(
                        f"File path is absolute: {arc_name!r}."
                    )
                    continue
                normalized = _normalized_archive_path(arc_name)
                # Traversal
                if normalized.startswith(".."):
                    result.errors.append(
                        f"Path traversal detected: {arc_name!r} normalizes to {normalized!r}."
                    )
                    continue
                archive_lower = normalized.lower()
                if archive_lower in seen_archive_normalized:
                    result.errors.append(
                        f"Duplicate path after normalization: {arc_name!r}."
                    )
                seen_archive_normalized.add(archive_lower)

            entries = _discover_skill_entries(zf)
            if not entries:
                result.errors.append("No SKILL.md found in archive.")
                return result  # cannot proceed further

            skill_names: set[str] = set()
            for entry in entries:
                skill_label = entry.root or "."
                try:
                    raw_skill_md = zf.read(entry.skill_md_path).decode("utf-8")
                except Exception as exc:
                    result.errors.append(f"Cannot read {entry.skill_md_path}: {exc}")
                    continue

                fm, _body = _parse_skill_md(raw_skill_md)

                name = str(fm.get("name", "")).strip()
                description = str(fm.get("description", "")).strip()
                if not name:
                    result.errors.append(
                        f"{skill_label}: Frontmatter field 'name' is missing or empty."
                    )
                else:
                    name_key = name.lower()
                    if name_key in skill_names:
                        result.errors.append(
                            f"{skill_label}: Duplicate skill name in archive: {name!r}."
                        )
                    skill_names.add(name_key)
                if not description:
                    result.errors.append(
                        f"{skill_label}: Frontmatter field 'description' is missing or empty."
                    )

                # Resource path safety checks within this skill package root.
                seen_resource_normalized: set[str] = set()
                for arc_name, rel in _resource_entries_for_skill(zf, entry, entries):
                    if posixpath.isabs(rel):
                        result.errors.append(
                            f"{skill_label}: File path is absolute: {arc_name!r}."
                        )
                        continue
                    normalized = posixpath.normpath(rel)
                    if normalized.startswith(".."):
                        result.errors.append(
                            f"{skill_label}: Path traversal detected: {arc_name!r} "
                            f"normalizes to {normalized!r}."
                        )
                        continue
                    lower = normalized.lower()
                    if lower in seen_resource_normalized:
                        result.errors.append(
                            f"{skill_label}: Duplicate path after normalization: {arc_name!r}."
                        )
                    seen_resource_normalized.add(lower)

                # Warnings
                if fm.get("dependencies"):
                    result.warnings.append(
                        f"{skill_label}: Frontmatter field 'dependencies' is deprecated "
                        "and will be ignored."
                    )
                if fm.get("runtime"):
                    result.warnings.append(
                        f"{skill_label}: Frontmatter field 'runtime' is deprecated "
                        "and will be ignored."
                    )
                unknown_keys = set(fm.keys()) - _KNOWN_FM_KEYS
                for k in sorted(unknown_keys):
                    result.warnings.append(
                        f"{skill_label}: Unknown frontmatter field: {k!r}."
                    )
                if fm.get("allowed-tools") or fm.get("allowed_tools"):
                    result.warnings.append(
                        f"{skill_label}: Frontmatter field 'allowed-tools' is present "
                        "but not enforced."
                    )
                if _body and len(_body.encode("utf-8")) > 50 * 1024:
                    result.warnings.append(f"{skill_label}: SKILL.md body exceeds 50 KB.")

        return result

    # ------------------------------------------------------------------
    # import_package
    # ------------------------------------------------------------------

    @staticmethod
    def import_package(
        db: "Session",
        app_id: int,
        zip_bytes: bytes,
        *,
        source: str = "upload",
    ):
        """Parse and store an Agent Skills ZIP package, returning the first skill.

        Silently drops deprecated 'dependencies' and 'runtime' frontmatter fields.
        Accepts the legacy ``files/<path>`` layout and normalizes to package-root paths.
        If the archive contains multiple skill folders, all are imported and the
        first discovered skill is returned for backward compatibility.

        Returns:
            The created or updated :class:`~models.skill.Skill` instance.

        Raises:
            ValueError: If validation fails.
        """
        imported = SkillPackageRepository.import_packages(
            db,
            app_id,
            zip_bytes,
            source=source,
        )
        return imported[0]

    @staticmethod
    def import_packages(
        db: "Session",
        app_id: int,
        zip_bytes: bytes,
        *,
        source: str = "upload",
    ) -> list:
        """Parse and store every Agent Skill package discovered in a ZIP.

        Each folder containing ``SKILL.md`` or ``skill.md`` is treated as an
        independent skill package. Resources are imported from that folder
        relative to the manifest location. Nested skill packages are excluded
        from the parent skill's resources.
        """
        from models.skill import Skill
        from repositories.skill_repository import SkillRepository

        validation = SkillPackageRepository.validate_package(zip_bytes)
        if not validation.is_valid:
            raise ValueError(f"Invalid skill package: {validation.errors}")

        imported_skills = []
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            entries = _discover_skill_entries(zf)
            for entry in entries:
                raw_skill_md = zf.read(entry.skill_md_path).decode("utf-8")
                fm, body = _parse_skill_md(raw_skill_md)

                # Silently drop deprecated fields
                fm.pop("dependencies", None)
                fm.pop("runtime", None)

                name = str(fm.get("name", "")).strip()
                description = str(fm.get("description", "")).strip()

                # Resolve existing owned skill by name
                existing = db.query(Skill).filter(
                    Skill.app_id == app_id,
                    Skill.name == name,
                ).first()

                if existing:
                    skill = existing
                else:
                    from services.tier_enforcement_service import TierEnforcementService
                    TierEnforcementService.check_resource_limit(db, app_id, "skills")
                    from datetime import datetime
                    skill = Skill()
                    skill.app_id = app_id
                    skill.create_date = datetime.now()

                skill.name = name
                skill.display_name = fm.get("display_name")
                skill.description = description
                skill.content = body
                import json
                _tools = fm.get("allowed-tools") or fm.get("allowed_tools")
                skill.allowed_tools = json.dumps(_tools) if _tools else None
                skill.bootstrap_script_path = fm.get("bootstrap_script_path")
                _ro = fm.get("runtime_options")
                skill.runtime_options = json.dumps(_ro) if _ro else None

                # Steps 5.2 + 5.3: store when_to_use and disable_model_invocation as JSON
                # in the frontmatter column so the router can read them without a migration.
                _skill_fm: dict = {}
                _when_to_use = fm.get("when-to-use") or fm.get("when_to_use") or None
                if _when_to_use:
                    _skill_fm["when_to_use"] = str(_when_to_use)
                _disable_mi = bool(
                    fm.get("disable-model-invocation")
                    or fm.get("disable_model_invocation")
                    or False
                )
                _skill_fm["disable_model_invocation"] = _disable_mi
                skill.frontmatter = json.dumps(_skill_fm) if _skill_fm else None

                if existing:
                    skill = SkillRepository.update(db, skill)
                else:
                    skill = SkillRepository.create(db, skill)

                # Replace SkillFiles
                SkillRepository.delete_skill_files(db, skill.skill_id)
                for arc_name, rel in _resource_entries_for_skill(zf, entry, entries):
                    try:
                        _validate_skill_file_path(rel)
                    except ValueError:
                        continue  # validation already caught this; skip silently
                    raw = zf.read(arc_name)
                    media_type = _guess_media_type(rel)
                    try:
                        content_text = raw.decode("utf-8")
                        content_bytes = None
                    except UnicodeDecodeError:
                        content_text = None
                        content_bytes = raw
                    SkillRepository.upsert_skill_file(
                        db,
                        skill_id=skill.skill_id,
                        path=rel,
                        media_type=media_type,
                        content_text=content_text,
                        content_bytes=content_bytes,
                        checksum_sha256=_sha256_hex(raw),
                    )

                db.refresh(skill)
                imported_skills.append(skill)

        return imported_skills

    # ------------------------------------------------------------------
    # export_package
    # ------------------------------------------------------------------

    @staticmethod
    def export_package(db: "Session", app_id: int, skill_id: int) -> bytes:
        """Return a canonical ZIP with SKILL.md at root and resources at package-root paths.

        The exported archive uses the v2 layout (no ``files/`` prefix). Deprecated
        fields ``dependencies`` and ``runtime`` are NOT included in the SKILL.md
        frontmatter.

        Raises:
            ValueError: If the skill is not found.
        """
        from models.skill import Skill
        from sqlalchemy import or_

        skill = db.query(Skill).filter(
            Skill.skill_id == skill_id,
            or_(Skill.app_id == app_id, Skill.app_id.is_(None)),
        ).first()
        if skill is None:
            raise ValueError(f"Skill {skill_id} not found for app {app_id}.")

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            # SKILL.md at archive root
            zf.writestr("SKILL.md", _build_skill_md(skill))

            # Bundled files at package-root-relative paths (no files/ prefix)
            for sf in skill.files or []:
                _validate_skill_file_path(sf.path)  # safety before export
                if sf.content_bytes is not None:
                    zf.writestr(sf.path, sf.content_bytes)
                elif sf.content_text is not None:
                    zf.writestr(sf.path, sf.content_text.encode("utf-8"))

        return buf.getvalue()

    # ------------------------------------------------------------------
    # get_catalog
    # ------------------------------------------------------------------

    @staticmethod
    def get_catalog(db: "Session", app_id: int) -> list[SkillCatalogItem]:
        """Return router-safe metadata only — no body, content, or file data."""
        from models.skill import Skill
        from sqlalchemy import or_

        import json

        skills = db.query(Skill).filter(
            or_(Skill.app_id == app_id, Skill.app_id.is_(None))
        ).all()
        result = []
        for s in skills:
            fm: dict = {}
            if s.frontmatter:
                try:
                    fm = json.loads(s.frontmatter)
                except Exception:
                    pass
            result.append(
                SkillCatalogItem(
                    skill_id=s.skill_id,
                    name=s.name,
                    description=s.description or "",
                    when_to_use=fm.get("when_to_use"),
                    disable_model_invocation=bool(fm.get("disable_model_invocation", False)),
                )
            )
        return result

    # ------------------------------------------------------------------
    # get_activation_payload
    # ------------------------------------------------------------------

    @staticmethod
    def get_activation_payload(
        db: "Session",
        app_id: int,
        skill_name: str,
    ) -> Optional[SkillActivationPayload]:
        """Return skill body, frontmatter, package-root metadata, and resource listing."""
        from models.skill import Skill
        from sqlalchemy import or_

        skill = db.query(Skill).filter(
            Skill.name == skill_name,
            or_(Skill.app_id == app_id, Skill.app_id.is_(None)),
        ).first()
        if skill is None:
            return None

        import json

        def _from_json(v):
            if v is None:
                return None
            if isinstance(v, (list, dict)):
                return v
            try:
                return json.loads(v)
            except Exception:
                return None

        fm = {
            "name": skill.name,
            "description": skill.description or "",
        }
        if skill.display_name:
            fm["display_name"] = skill.display_name
        if skill.allowed_tools:
            fm["allowed_tools"] = _from_json(skill.allowed_tools)
        if skill.bootstrap_script_path:
            fm["bootstrap_script_path"] = skill.bootstrap_script_path

        return SkillActivationPayload(
            skill_id=skill.skill_id,
            name=skill.name,
            body=skill.content or "",
            frontmatter=fm,
            files_dir="",  # package root
            file_paths=[sf.path for sf in (skill.files or [])],
        )

    # ------------------------------------------------------------------
    # list_files
    # ------------------------------------------------------------------

    @staticmethod
    def list_files(db: "Session", skill_id: int) -> list[SkillFileSummary]:
        """Return package-root-relative file summaries."""
        from models.skill import SkillFile

        files = db.query(SkillFile).filter(SkillFile.skill_id == skill_id).all()
        result = []
        for sf in files:
            if sf.content_bytes is not None:
                size = len(sf.content_bytes)
            elif sf.content_text is not None:
                size = len(sf.content_text.encode("utf-8"))
            else:
                size = 0
            result.append(SkillFileSummary(path=sf.path, size_bytes=size))
        return result

    # ------------------------------------------------------------------
    # read_file
    # ------------------------------------------------------------------

    @staticmethod
    def read_file(db: "Session", skill_id: int, path: str) -> SkillFileContent:
        """Return content of one bundled resource.

        Validates *path* with :func:`_validate_skill_file_path` before access.

        Raises:
            ValueError: If path is unsafe or the file is not found.
        """
        from models.skill import SkillFile

        _validate_skill_file_path(path)
        sf = db.query(SkillFile).filter(
            SkillFile.skill_id == skill_id,
            SkillFile.path == path,
        ).first()
        if sf is None:
            raise ValueError(f"File not found: skill_id={skill_id}, path={path!r}")

        if sf.content_bytes is not None:
            content = sf.content_bytes
        elif sf.content_text is not None:
            content = sf.content_text.encode("utf-8")
        else:
            content = b""

        return SkillFileContent(
            path=sf.path,
            content=content,
            mime_type=sf.media_type or _guess_media_type(sf.path) or "application/octet-stream",
        )
