import hashlib
import posixpath
from typing import Dict, Iterable, List, Literal, Optional, Set, Tuple, Union

from sqlalchemy import delete, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, undefer
from sqlalchemy.orm.util import identity_key

from models.skill import Skill, SkillFile
from utils.skill_paths import normalize_path as normalize_skill_path

_MAX_MEDIA_TYPE_LENGTH = 120

_TEXT_MEDIA_TYPES = {'application/json', 'application/x-yaml', 'application/xml'}
_TEXT_EXTENSIONS = {
    '.md', '.txt', '.py', '.sh', '.json', '.yaml', '.yml', '.csv', '.toml', '.ini', '.cfg',
    '.js', '.ts', '.html', '.css', '.sql',
}


class SkillPackageRepository:
    """Repository class for SkillFile (skill package file) database operations"""

    @staticmethod
    def normalize_path(path: str) -> str:
        """Normalise a package-root-relative path to POSIX form (delegates to ``utils.skill_paths``).

        Raises:
            ValueError: See ``utils.skill_paths.normalize_path``; a root-level ``SKILL.md`` is rejected.
        """
        return normalize_skill_path(path)

    @staticmethod
    def compute_checksum(data: bytes) -> str:
        """Return the SHA-256 hex digest of ``data``."""
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def classify(
        path: str, data: bytes, media_type: Optional[str]
    ) -> Tuple[Literal['text', 'binary'], Union[str, bytes]]:
        """Classify file content as text (decoded ``str``) or binary (raw ``bytes``)."""
        mt = (media_type or '').split(';', 1)[0].strip().lower()
        text_hint = (
            mt.startswith('text/')
            or mt in _TEXT_MEDIA_TYPES
            or mt.endswith('+json')
            or mt.endswith('+xml')
            or posixpath.splitext(path.lower())[1] in _TEXT_EXTENSIONS
        )
        if text_hint and b'\x00' not in data:
            try:
                return 'text', data.decode('utf-8')
            except UnicodeDecodeError:
                pass
        return 'binary', data

    @staticmethod
    def list_files(db: Session, skill_id: int) -> List[SkillFile]:
        """List all files of a skill with content loaded (materialisation paths only).

        Note: skill_id is NOT app-scoped: callers must first resolve the skill via
        SkillRepository.get_by_id_and_app_id.
        """
        return (
            db.query(SkillFile)
            .options(undefer(SkillFile.content_text), undefer(SkillFile.content_bytes))
            .filter(SkillFile.skill_id == skill_id)
            .order_by(SkillFile.path)
            .all()
        )

    @staticmethod
    def list_paths(db: Session, skill_id: int) -> List[Tuple[str, Optional[str], int, str, bool]]:
        """List ``(path, media_type, size_bytes, checksum, is_text)`` without loading blobs.

        ``is_text`` is a boolean SQL expression (``content_text IS NOT NULL``); blobs stay in the database.

        Note: skill_id is NOT app-scoped: callers must first resolve the skill via
        SkillRepository.get_by_id_and_app_id.
        """
        rows = (
            db.query(
                SkillFile.path,
                SkillFile.media_type,
                func.coalesce(
                    func.octet_length(SkillFile.content_bytes),
                    func.octet_length(SkillFile.content_text),
                    0,
                ),
                SkillFile.checksum_sha256,
                SkillFile.content_text.isnot(None),
            )
            .filter(SkillFile.skill_id == skill_id)
            .order_by(SkillFile.path)
            .all()
        )
        return [(r[0], r[1], int(r[2]), r[3], bool(r[4])) for r in rows]

    @staticmethod
    def get_file(db: Session, skill_id: int, path: str) -> Optional[SkillFile]:
        """Get one file of a skill by its (already normalised) path, with content loaded.

        Note: skill_id is NOT app-scoped: callers must first resolve the skill via
        SkillRepository.get_by_id_and_app_id.
        """
        return (
            db.query(SkillFile)
            .options(undefer(SkillFile.content_text), undefer(SkillFile.content_bytes))
            .filter(SkillFile.skill_id == skill_id, SkillFile.path == path)
            .first()
        )

    @staticmethod
    def _normalize_media_type(media_type: Optional[str]) -> Optional[str]:
        """Strip parameters, lowercase, blank -> None. Raises ValueError if longer than 120 chars."""
        if media_type is None:
            return None
        mt = media_type.split(';', 1)[0].strip().lower()
        if not mt:
            return None
        if len(mt) > _MAX_MEDIA_TYPE_LENGTH:
            raise ValueError(f"Media type exceeds {_MAX_MEDIA_TYPE_LENGTH} characters.")
        return mt

    @staticmethod
    def replace_files(
        db: Session,
        skill_id: int,
        files: Iterable[Tuple[str, bytes, Optional[str]]],
    ) -> int:
        """Replace all files of a skill. Flushes only; the caller owns the transaction.

        Note: skill_id is NOT app-scoped: callers must first resolve the skill via
        SkillRepository.get_by_id_and_app_id.

        Raises:
            ValueError: On an invalid path or media type, a duplicate path within the batch
                (case-insensitive) or a database integrity failure. After it raises, the caller
                must roll back the session.
        """
        prepared: List[SkillFile] = []
        seen: Set[str] = set()
        for raw_path, data, raw_media_type in files:
            path = SkillPackageRepository.normalize_path(raw_path)
            key = path.lower()
            if key in seen:
                raise ValueError(f"Duplicate skill file path: {path!r}")
            seen.add(key)
            media_type = SkillPackageRepository._normalize_media_type(raw_media_type)
            kind, content = SkillPackageRepository.classify(path, data, media_type)
            text_value = content if kind == 'text' else None
            bytes_value = content if kind == 'binary' else None
            if (text_value is None) == (bytes_value is None):
                raise ValueError("Invalid skill package contents.")
            prepared.append(SkillFile(
                skill_id=skill_id,
                path=path,
                media_type=media_type,
                content_text=text_value,
                content_bytes=bytes_value,
                checksum_sha256=SkillPackageRepository.compute_checksum(data),
            ))

        SkillPackageRepository.delete_all_for_skill(db, skill_id)
        db.add_all(prepared)
        try:
            db.flush()
        except IntegrityError:
            raise ValueError('Invalid skill package contents.') from None
        return len(prepared)

    @staticmethod
    def delete_all_for_skill(db: Session, skill_id: int) -> int:
        """Bulk-delete all files of a skill. Returns the number of deleted rows.

        Note: skill_id is NOT app-scoped: callers must first resolve the skill via
        SkillRepository.get_by_id_and_app_id.
        """
        result = db.execute(
            delete(SkillFile).where(SkillFile.skill_id == skill_id),
            execution_options={'synchronize_session': 'fetch'},
        )
        # Keep an already-loaded Skill.files collection from serving stale rows (no extra query if not loaded).
        skill = db.identity_map.get(identity_key(Skill, skill_id))
        if skill is not None:
            db.expire(skill, ['files'])
        return result.rowcount or 0

    @staticmethod
    def count_by_skill_ids(db: Session, skill_ids: Iterable[int]) -> Dict[int, int]:
        """Return ``{skill_id: file_count}`` using a single grouped query.

        Note: skill_id is NOT app-scoped: callers must first resolve the skill via
        SkillRepository.get_by_id_and_app_id.
        """
        ids = list(skill_ids)
        if not ids:
            return {}
        rows = (
            db.query(SkillFile.skill_id, func.count())
            .filter(SkillFile.skill_id.in_(ids))
            .group_by(SkillFile.skill_id)
            .all()
        )
        return {sid: cnt for sid, cnt in rows}
