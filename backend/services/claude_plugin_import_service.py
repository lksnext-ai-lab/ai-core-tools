"""Import Claude Code plugin ZIPs into an application.

Only passive components are imported: skills and agent markdown definitions.
Executable plugin components such as hooks, monitors, MCP servers, and bin
entries are intentionally ignored.
"""

from __future__ import annotations

import io
import json
import posixpath
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from models.agent import (
    Agent,
    AgentSkill,
    DEFAULT_AGENT_TEMPERATURE,
    DEFAULT_MEMORY_SUMMARIZE_THRESHOLD,
)
from models.skill import Skill, SkillFile
from repositories.skill_package_repository import (
    _guess_media_type,
    _parse_skill_md,
    _sha256_hex,
    _validate_skill_file_path,
)
from services.tier_enforcement_service import TierEnforcementService

_MAX_TOTAL_BYTES = 50 * 1024 * 1024
_MAX_FILE_COUNT = 500
_MAX_SINGLE_FILE_BYTES = 10 * 1024 * 1024
_MAX_DECOMPRESS_RATIO = 100


@dataclass(frozen=True)
class ClaudePluginImportedSkill:
    skill_id: int
    name: str
    created: bool


@dataclass(frozen=True)
class ClaudePluginImportedAgent:
    agent_id: int
    name: str
    created: bool
    skill_ids: list[int] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ClaudePluginImportResult:
    plugin_name: Optional[str]
    imported_skills: list[ClaudePluginImportedSkill]
    imported_agents: list[ClaudePluginImportedAgent]
    warnings: list[str]


@dataclass(frozen=True)
class _SkillEntry:
    root: str
    skill_md_path: str
    is_command: bool = False


@dataclass(frozen=True)
class _AgentEntry:
    path: str


class ClaudePluginImportService:
    """Imports Claude Code plugin skills and agents into an app."""

    def __init__(self, session: Session):
        self.session = session

    def import_plugin(self, app_id: int, zip_bytes: bytes) -> ClaudePluginImportResult:
        """Import skills and agents from a Claude Code plugin ZIP."""
        warnings: list[str] = []

        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        except zipfile.BadZipFile as exc:
            raise ValueError(f"Cannot open ZIP: {exc}") from exc

        with zf:
            self._validate_archive(zf, len(zip_bytes))
            plugin_root, manifest = self._load_manifest(zf)
            plugin_name = self._plugin_name(plugin_root, manifest)

            skill_entries = self._discover_skill_entries(zf, plugin_root, manifest)
            agent_entries = self._discover_agent_entries(zf, plugin_root, manifest)

            if not skill_entries and not agent_entries:
                raise ValueError("Claude plugin contains no importable skills or agents.")

            imported_skills, skill_ids_by_name = self._import_skills(
                zf,
                app_id,
                plugin_root,
                skill_entries,
                warnings,
            )
            imported_agents = self._import_agents(
                zf,
                app_id,
                agent_entries,
                skill_ids_by_name,
                warnings,
            )

        self.session.commit()
        return ClaudePluginImportResult(
            plugin_name=plugin_name,
            imported_skills=imported_skills,
            imported_agents=imported_agents,
            warnings=warnings,
        )

    def _validate_archive(self, zf: zipfile.ZipFile, compressed_size: int) -> None:
        infos = zf.infolist()
        errors: list[str] = []

        if len(infos) > _MAX_FILE_COUNT:
            errors.append(
                f"Archive exceeds maximum file count ({len(infos)} > {_MAX_FILE_COUNT})."
            )

        total_bytes = 0
        seen: set[str] = set()
        for info in infos:
            total_bytes += info.file_size
            if info.file_size > _MAX_SINGLE_FILE_BYTES:
                errors.append(
                    f"File '{info.filename}' exceeds maximum size "
                    f"({info.file_size} > {_MAX_SINGLE_FILE_BYTES})."
                )
            normalized = self._normalize_archive_path(info.filename)
            if (
                normalized.startswith("..")
                or posixpath.isabs(info.filename)
                or posixpath.isabs(normalized)
            ):
                errors.append(f"Path traversal detected: {info.filename!r}.")
                continue
            lower = normalized.lower()
            if not info.is_dir() and lower in seen:
                errors.append(f"Duplicate path after normalization: {info.filename!r}.")
            seen.add(lower)

        if total_bytes > _MAX_TOTAL_BYTES:
            errors.append(
                f"Archive total decompressed size exceeds limit "
                f"({total_bytes} > {_MAX_TOTAL_BYTES})."
            )
        if compressed_size > 0 and total_bytes > compressed_size * _MAX_DECOMPRESS_RATIO:
            errors.append("Archive decompression ratio exceeds limit (possible zip bomb).")

        if errors:
            raise ValueError(f"Invalid Claude plugin package: {errors}")

    def _load_manifest(self, zf: zipfile.ZipFile) -> tuple[str, dict[str, Any]]:
        manifest_paths = [
            self._normalize_archive_path(info.filename)
            for info in zf.infolist()
            if not info.is_dir()
            and self._normalize_archive_path(info.filename).endswith(
                ".claude-plugin/plugin.json"
            )
        ]

        if len(manifest_paths) > 1:
            raise ValueError("Archive contains multiple Claude plugin manifests.")

        if manifest_paths:
            manifest_path = manifest_paths[0]
            plugin_root = manifest_path[: -len(".claude-plugin/plugin.json")].rstrip("/")
            try:
                manifest = json.loads(zf.read(manifest_path).decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid Claude plugin manifest JSON: {exc}") from exc
            if not isinstance(manifest, dict):
                raise ValueError("Claude plugin manifest must be a JSON object.")
            return plugin_root, manifest

        return self._infer_plugin_root(zf), {}

    def _infer_plugin_root(self, zf: zipfile.ZipFile) -> str:
        paths = [
            self._normalize_archive_path(info.filename)
            for info in zf.infolist()
            if not info.is_dir()
        ]
        if any(path.startswith(("skills/", "agents/", "commands/")) for path in paths):
            return ""

        first_segments = {
            path.split("/", 1)[0]
            for path in paths
            if "/" in path and not path.startswith(".")
        }
        if len(first_segments) == 1:
            candidate = next(iter(first_segments))
            prefix = f"{candidate}/"
            if any(
                path.startswith(
                    (f"{prefix}skills/", f"{prefix}agents/", f"{prefix}commands/")
                )
                for path in paths
            ):
                return candidate
        return ""

    def _plugin_name(self, plugin_root: str, manifest: dict[str, Any]) -> Optional[str]:
        name = manifest.get("displayName") or manifest.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
        if plugin_root:
            return PurePosixPath(plugin_root).name
        return None

    def _discover_skill_entries(
        self,
        zf: zipfile.ZipFile,
        plugin_root: str,
        manifest: dict[str, Any],
    ) -> list[_SkillEntry]:
        search_dirs = ["skills"]
        search_dirs.extend(self._manifest_paths(manifest.get("skills")))

        entries: dict[str, _SkillEntry] = {}
        for rel_dir in search_dirs:
            rel_dir = self._normalize_relative_path(rel_dir)
            for info in zf.infolist():
                if info.is_dir():
                    continue
                path = self._normalize_archive_path(info.filename)
                rel = self._relative_to_plugin_root(path, plugin_root)
                if rel is None:
                    continue
                if posixpath.basename(rel).lower() != "skill.md":
                    continue
                if rel_dir and not self._is_descendant(rel, rel_dir):
                    continue
                root = posixpath.dirname(rel)
                entries[root.lower()] = _SkillEntry(root=root, skill_md_path=path)

        commands = manifest.get("commands") if "commands" in manifest else "commands"
        for command_path in self._manifest_paths(commands):
            command_path = self._normalize_relative_path(command_path)
            for path in self._matching_markdown_files(zf, plugin_root, command_path):
                rel = self._relative_to_plugin_root(path, plugin_root)
                if rel is None:
                    continue
                key = f"command:{rel.lower()}"
                entries[key] = _SkillEntry(
                    root=posixpath.dirname(rel),
                    skill_md_path=path,
                    is_command=True,
                )

        return sorted(entries.values(), key=lambda entry: entry.skill_md_path)

    def _discover_agent_entries(
        self,
        zf: zipfile.ZipFile,
        plugin_root: str,
        manifest: dict[str, Any],
    ) -> list[_AgentEntry]:
        configured = manifest.get("agents") if "agents" in manifest else "agents"
        entries = {
            path.lower(): _AgentEntry(path=path)
            for configured_path in self._manifest_paths(configured)
            for path in self._matching_markdown_files(
                zf,
                plugin_root,
                self._normalize_relative_path(configured_path),
            )
        }
        return sorted(entries.values(), key=lambda entry: entry.path)

    def _matching_markdown_files(
        self,
        zf: zipfile.ZipFile,
        plugin_root: str,
        configured_path: str,
    ) -> list[str]:
        matches: list[str] = []
        configured_path = configured_path.rstrip("/")
        for info in zf.infolist():
            if info.is_dir():
                continue
            path = self._normalize_archive_path(info.filename)
            rel = self._relative_to_plugin_root(path, plugin_root)
            if rel is None or not rel.lower().endswith(".md"):
                continue
            if rel == configured_path or self._is_descendant(rel, configured_path):
                matches.append(path)
        return matches

    def _import_skills(
        self,
        zf: zipfile.ZipFile,
        app_id: int,
        plugin_root: str,
        entries: list[_SkillEntry],
        warnings: list[str],
    ) -> tuple[list[ClaudePluginImportedSkill], dict[str, int]]:
        imported: list[ClaudePluginImportedSkill] = []
        skill_ids_by_name: dict[str, int] = {
            skill.name.lower(): skill.skill_id
            for skill in self.session.query(Skill)
            .filter(or_(Skill.app_id == app_id, Skill.app_id.is_(None)))
            .all()
        }
        skill_roots = [entry.root for entry in entries if not entry.is_command]

        for entry in entries:
            raw = zf.read(entry.skill_md_path).decode("utf-8")
            fm, body = _parse_skill_md(raw)
            fallback_name = PurePosixPath(entry.root).name
            if entry.is_command:
                fallback_name = PurePosixPath(entry.skill_md_path).stem

            name = str(fm.get("name") or fallback_name).strip()
            if not name:
                warnings.append(f"Skipped skill at {entry.skill_md_path}: missing name.")
                continue

            description = str(fm.get("description") or "").strip()
            if not description:
                description = f"Imported from Claude plugin component {name}."

            existing = (
                self.session.query(Skill)
                .filter(Skill.app_id == app_id, Skill.name == name)
                .first()
            )
            created = existing is None
            if created:
                TierEnforcementService.check_resource_limit(
                    self.session, app_id, "skills"
                )
                skill = Skill(app_id=app_id, create_date=datetime.now())
                self.session.add(skill)
            else:
                skill = existing

            skill.name = name
            skill.display_name = fm.get("display_name")
            skill.description = description
            skill.content = body
            skill.allowed_tools = self._json_or_none(
                fm.get("allowed-tools") or fm.get("allowed_tools")
            )
            skill.bootstrap_script_path = fm.get("bootstrap_script_path")
            skill.runtime_options = self._json_or_none(fm.get("runtime_options"))
            skill.frontmatter = self._json_or_none(
                {
                    "claude_plugin_path": entry.skill_md_path,
                    "disable_model_invocation": bool(
                        fm.get("disable-model-invocation")
                        or fm.get("disable_model_invocation")
                        or False
                    ),
                    **(
                        {"when_to_use": str(fm.get("when-to-use") or fm.get("when_to_use"))}
                        if fm.get("when-to-use") or fm.get("when_to_use")
                        else {}
                    ),
                }
            )

            self.session.flush()
            if entry.is_command:
                self.session.query(SkillFile).filter(
                    SkillFile.skill_id == skill.skill_id
                ).delete(synchronize_session=False)
            else:
                self._replace_skill_files(
                    zf, plugin_root, entry, skill.skill_id, skill_roots
                )
            self.session.flush()

            imported.append(
                ClaudePluginImportedSkill(
                    skill_id=skill.skill_id,
                    name=skill.name,
                    created=created,
                )
            )
            skill_ids_by_name[skill.name.lower()] = skill.skill_id

        return imported, skill_ids_by_name

    def _replace_skill_files(
        self,
        zf: zipfile.ZipFile,
        plugin_root: str,
        entry: _SkillEntry,
        skill_id: int,
        skill_roots: list[str],
    ) -> None:
        self.session.query(SkillFile).filter(SkillFile.skill_id == skill_id).delete(
            synchronize_session=False
        )

        entry_rel = self._relative_to_plugin_root(entry.skill_md_path, plugin_root)
        if entry_rel is None:
            return
        skill_root = posixpath.dirname(entry_rel)
        nested_roots = [
            root
            for root in skill_roots
            if root and root != skill_root and self._is_descendant(root, skill_root)
        ]

        for info in zf.infolist():
            if info.is_dir():
                continue
            path = self._normalize_archive_path(info.filename)
            rel = self._relative_to_plugin_root(path, plugin_root)
            if rel is None or rel == entry_rel:
                continue
            if skill_root and not self._is_descendant(rel, skill_root):
                continue
            if not skill_root:
                continue
            if any(self._is_descendant(rel, nested_root) for nested_root in nested_roots):
                continue

            package_rel = rel[len(skill_root) :].lstrip("/")
            if not package_rel:
                continue
            _validate_skill_file_path(package_rel)
            raw = zf.read(path)
            try:
                content_text = raw.decode("utf-8")
                content_bytes = None
            except UnicodeDecodeError:
                content_text = None
                content_bytes = raw
            self.session.add(
                SkillFile(
                    skill_id=skill_id,
                    path=package_rel,
                    media_type=_guess_media_type(package_rel),
                    content_text=content_text,
                    content_bytes=content_bytes,
                    checksum_sha256=_sha256_hex(raw),
                )
            )

    def _import_agents(
        self,
        zf: zipfile.ZipFile,
        app_id: int,
        entries: list[_AgentEntry],
        skill_ids_by_name: dict[str, int],
        warnings: list[str],
    ) -> list[ClaudePluginImportedAgent]:
        imported: list[ClaudePluginImportedAgent] = []

        for entry in entries:
            raw = zf.read(entry.path).decode("utf-8")
            fm, body = _parse_skill_md(raw)
            name = str(fm.get("name") or PurePosixPath(entry.path).stem).strip()
            if not name:
                warnings.append(f"Skipped agent at {entry.path}: missing name.")
                continue

            description = str(fm.get("description") or "").strip()
            requested_skills = self._coerce_string_list(fm.get("skills"))
            skill_ids: list[int] = []
            missing_skills: list[str] = []
            for skill_name in requested_skills:
                skill_id = skill_ids_by_name.get(skill_name.lower())
                if skill_id:
                    skill_ids.append(skill_id)
                else:
                    missing_skills.append(skill_name)

            existing = (
                self.session.query(Agent)
                .filter(Agent.app_id == app_id, Agent.name == name)
                .first()
            )
            created = existing is None
            if created:
                TierEnforcementService.check_resource_limit(
                    self.session, app_id, "agents"
                )
                agent = Agent(app_id=app_id, create_date=datetime.now(), type="agent")
                self.session.add(agent)
            else:
                agent = existing

            agent.name = name
            agent.description = description
            agent.system_prompt = body
            agent.prompt_template = ""
            agent.has_memory = bool(fm.get("memory") or False)
            agent.memory_max_messages = 20
            agent.memory_max_tokens = 4000
            agent.memory_summarize_threshold = DEFAULT_MEMORY_SUMMARIZE_THRESHOLD
            agent.temperature = DEFAULT_AGENT_TEMPERATURE
            agent.request_count = agent.request_count or 0
            agent.is_tool = False
            agent.status = agent.status or "active"

            self.session.flush()
            self._replace_agent_skill_links(agent.agent_id, skill_ids)
            self.session.flush()

            if missing_skills:
                warnings.append(
                    f"Agent '{name}' references missing skills: "
                    f"{', '.join(missing_skills)}."
                )

            imported.append(
                ClaudePluginImportedAgent(
                    agent_id=agent.agent_id,
                    name=agent.name,
                    created=created,
                    skill_ids=skill_ids,
                    missing_skills=missing_skills,
                )
            )

        return imported

    def _replace_agent_skill_links(self, agent_id: int, skill_ids: list[int]) -> None:
        self.session.query(AgentSkill).filter(AgentSkill.agent_id == agent_id).delete(
            synchronize_session=False
        )
        for skill_id in dict.fromkeys(skill_ids):
            self.session.add(AgentSkill(agent_id=agent_id, skill_id=skill_id))

    def _manifest_paths(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [item for item in value if isinstance(item, str)]
        return []

    def _coerce_string_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        if isinstance(value, list):
            names: list[str] = []
            for item in value:
                if isinstance(item, str) and item.strip():
                    names.append(item.strip())
                elif isinstance(item, dict) and isinstance(item.get("name"), str):
                    names.append(item["name"].strip())
            return [name for name in names if name]
        return []

    def _json_or_none(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        return json.dumps(value)

    def _normalize_archive_path(self, path: str) -> str:
        return posixpath.normpath(path.replace("\\", "/"))

    def _normalize_relative_path(self, path: str) -> str:
        raw = path.strip().replace("\\", "/")
        normalized = posixpath.normpath(raw)
        if normalized == ".":
            return ""
        if normalized.startswith("..") or posixpath.isabs(raw):
            raise ValueError(f"Manifest path escapes plugin root: {path!r}.")
        return normalized.rstrip("/")

    def _relative_to_plugin_root(self, path: str, plugin_root: str) -> Optional[str]:
        path = self._normalize_archive_path(path)
        if not plugin_root:
            return path
        if path == plugin_root:
            return ""
        prefix = f"{plugin_root}/"
        if path.startswith(prefix):
            return path[len(prefix) :]
        return None

    def _is_descendant(self, path: str, root: str) -> bool:
        if not root:
            return True
        return path == root or path.startswith(f"{root.rstrip('/')}/")
