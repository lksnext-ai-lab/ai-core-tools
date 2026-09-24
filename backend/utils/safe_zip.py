"""Hardened, fully in-memory zip reader for skill package import.

Nothing is ever written to disk. Supported entry point for imports: ``read_safe_zip`` (all-or-nothing).

Defence layers, in order:
1. Uploaded archive size cap (before any parsing).
2. End-Of-Central-Directory (EOCD, incl. ZIP64) declared entry count / directory size cap, checked on the raw
   bytes BEFORE ``zipfile`` builds one ``ZipInfo`` per entry.
3. Metadata checks on every entry (count, names, symlinks, encryption, compression method, duplicates, package
   root) before a single byte is decompressed. ``iter_safe_zip`` runs these eagerly, so the caller sees the error
   at call time, not on first iteration.
4. Streaming decompression in 64 KiB chunks; per-file, total and ratio limits are enforced on the bytes actually
   produced. Header sizes are only a cheap pre-check; the compressed size used for the cumulative ratio is the
   real uploaded archive length, never a header value.

Entry-name rules live in ``utils.skill_paths`` (shared with ``SkillPackageRepository``).
"""
import io
import stat
import struct
import zipfile
from typing import Dict, Iterator, List, NamedTuple, Optional, Set, Tuple

import config as settings
from utils.skill_paths import canonical_segments, normalize_path

_CHUNK_SIZE = 64 * 1024
_EOCD_SIG = b'PK\x05\x06'
_EOCD_LEN = 22
_ZIP64_LOCATOR_SIG = b'PK\x06\x07'
_ZIP64_LOCATOR_LEN = 20
_ZIP64_EOCD_SIG = b'PK\x06\x06'
_ZIP64_EOCD_LEN = 56
_MAX_COMMENT = 65535
# Upper bound on the central directory bytes per allowed entry (names are <= ~500 chars); bounds the number of
# ZipInfo objects even when the declared entry count lies.
_CD_BYTES_PER_ENTRY = 1024
_ENTRY_HARD_FACTOR = 4
# Ratio checks only apply once this many bytes have been streamed. Small, highly repetitive but legitimate
# files (a divider line, repetitive JSON) can exceed the ratio; bomb size is already bounded in absolute terms
# by the streamed max_file_bytes / max_total_bytes, so the ratio only needs to catch large expansions.
_RATIO_FLOOR_BYTES = 1024 * 1024
_ALLOWED_COMPRESSION = (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)

# Distinct, quotable failure reasons.
REASON_INVALID_ARCHIVE = 'invalid or corrupt zip archive'
REASON_ARCHIVE_TOO_LARGE = 'uploaded archive too large'
REASON_TOO_MANY_ENTRIES = 'too many archive entries'
REASON_TOO_MANY_FILES = 'too many files'
REASON_ABSOLUTE_PATH = 'absolute path in archive'
REASON_TRAVERSAL = 'path traversal in archive'
REASON_INVALID_PATH = 'invalid entry path'
REASON_SYMLINK = 'symlink entry not allowed'
REASON_ENCRYPTED = 'encrypted entry not allowed'
REASON_UNSUPPORTED_COMPRESSION = 'unsupported compression method'
REASON_DUPLICATE = 'duplicate entry name'
REASON_FILE_TOO_LARGE = 'file too large'
REASON_TOTAL_TOO_LARGE = 'archive too large when uncompressed'
REASON_RATIO = 'compression ratio too high'
REASON_NO_SKILL_MD = 'no SKILL.md at package root'


class SafeZipError(Exception):
    """A skill archive violated a safety rule (deliberately not a ``ValueError``).

    Attributes:
        reason: Stable, human-quotable description of the violation.
        limit: The numeric limit that tripped, as a string (e.g. ``'500'``), or ``None``.
        entry: Truncated offending entry name (raw, never interpolated unescaped into ``str(exc)``), or ``None``.
    """

    def __init__(self, reason: str, limit: Optional[str] = None, entry: Optional[str] = None) -> None:
        self.reason = reason
        self.limit = limit
        self.entry = entry[:200] if entry is not None else None
        parts = reason
        if self.entry is not None:
            parts += f': {self.entry!r}'
        if limit:
            parts += f' (limit {limit})'
        super().__init__(parts)


def _is_junk(segments: List[str]) -> bool:
    lowered = [s.lower() for s in segments]
    return '__macosx' in lowered or '.git' in lowered or (bool(lowered) and lowered[-1] == '.ds_store')


def _validated_name(raw_name: str) -> str:
    """Validate an entry name with the shared path rules; a root-level SKILL.md is allowed."""
    try:
        return normalize_path(raw_name, allow_root_skill_md=True)
    except ValueError as exc:
        absolute, segments = canonical_segments(raw_name)
        if absolute:
            reason = REASON_ABSOLUTE_PATH
        elif '..' in segments:
            reason = REASON_TRAVERSAL
        else:
            reason = REASON_INVALID_PATH
        raise SafeZipError(reason, entry=raw_name) from exc


def find_package_root(paths: List[str]) -> str:
    """Locate the package root inside a list of entry names.

    Must only be fed names yielded by ``iter_safe_zip`` (already normalised, ``/``-separated). Works with
    names before stripping the root (``['pkg/SKILL.md', 'pkg/a.py']``) and after (``['SKILL.md', 'a.py']``).

    Returns:
        ``''`` when ``SKILL.md`` is at the archive root, otherwise the single common top-level directory.

    Raises:
        SafeZipError: If neither case applies (including an empty list).
    """
    if any(p.lower() == 'skill.md' for p in paths):
        return ''
    tops = {p.split('/', 1)[0] for p in paths if '/' in p}
    if paths and len(tops) == 1 and all('/' in p for p in paths):
        top = next(iter(tops))
        if any(p.lower() == f'{top.lower()}/skill.md' for p in paths):
            return top
    raise SafeZipError(REASON_NO_SKILL_MD)


def strip_package_root(name: str, root: str) -> Optional[str]:
    """Return ``name`` relative to the package ``root``, re-normalised; ``None`` for the SKILL.md entry.

    Raises:
        SafeZipError: If ``name`` is not under ``root`` or the remainder is not a valid package path.
    """
    if root:
        prefix = root + '/'
        if not name.startswith(prefix):
            raise SafeZipError(REASON_INVALID_PATH, entry=name)
        rest = name[len(prefix):]
    else:
        rest = name
    if rest.lower() == 'skill.md':
        return None
    try:
        return normalize_path(rest)
    except ValueError as exc:
        raise SafeZipError(REASON_INVALID_PATH, entry=name) from exc


def find_plugin_root(paths: List[str]) -> str:
    """Locate the directory to strip before grouping a Claude Code plugin's ``skills/<name>/SKILL.md`` entries.

    Must only be fed names yielded by ``iter_safe_zip(..., require_skill_md=False)`` (already normalised,
    ``/``-separated). A Claude plugin bundle can hold several skills (unlike ``find_package_root``, which
    assumes exactly one), so this mirrors its shape rules for that different case rather than reusing it:

    - ``''`` when at least one entry already sits directly under a (case-insensitive) ``skills/`` directory
      at the archive root — nothing to strip.
    - the single common top-level segment ``T``, when every entry shares exactly one top-level segment and at
      least one matches ``T/skills/<name>/SKILL.md`` (case-insensitive) under it — the common "GitHub download
      ZIP" / ``zip -r plugin.zip my-plugin/`` wrapping-directory shape.
    - ``''`` otherwise. Unlike ``find_package_root`` this never raises: a plugin archive with no recognisable
      ``skills/`` directory at all is not this helper's failure to report — the caller (grouping zero
      candidates) reports its own "no skills found" error.
    """
    lowered = [p.lower() for p in paths]
    if any(p.startswith('skills/') for p in lowered):
        return ''
    tops = {p.split('/', 1)[0] for p in paths if '/' in p}
    if len(tops) == 1:
        top = next(iter(tops))
        prefix = f'{top.lower()}/skills/'
        if any(p.startswith(prefix) for p in lowered):
            return top
    return ''


def _check_eocd(data: bytes, max_entries: int) -> None:
    """Reject archives whose declared entry count / directory size exceeds the bound (raw-bytes check).

    Mirrors CPython ``zipfile``: when a valid ZIP64 locator sits right before the EOCD and a valid ZIP64 record
    sits where zipfile looks for it (``loc - 56``), zipfile REPLACES the 32-bit values with the ZIP64 ones, so the
    32-bit sentinels of always-ZIP64 writers are ignored. Otherwise the 32-bit values are used, and sentinels
    without a usable ZIP64 record are an invalid archive. A record at the offset named by the locator is only
    used to tighten the bound (max) when the zipfile-visible record is valid; on its own it is ignored, because
    zipfile would ignore it too and parse using the 32-bit values.
    """
    window_start = max(0, len(data) - (_MAX_COMMENT + _EOCD_LEN + 1))
    idx = data.rfind(_EOCD_SIG, window_start)
    if idx < 0 or idx + _EOCD_LEN > len(data):
        raise SafeZipError(REASON_INVALID_ARCHIVE)
    entries = struct.unpack_from('<H', data, idx + 10)[0]
    cd_size = struct.unpack_from('<I', data, idx + 12)[0]

    loc = idx - _ZIP64_LOCATOR_LEN
    zip64: Optional[Tuple[int, int]] = None
    if loc >= 0 and data[loc:loc + 4] == _ZIP64_LOCATOR_SIG:
        rec = loc - _ZIP64_EOCD_LEN  # where CPython zipfile looks (assumes no extensible data)
        if rec >= 0 and data[rec:rec + 4] == _ZIP64_EOCD_SIG:
            zip64 = (struct.unpack_from('<Q', data, rec + 32)[0], struct.unpack_from('<Q', data, rec + 40)[0])
            declared = struct.unpack_from('<Q', data, loc + 8)[0]
            if (
                declared != rec
                and declared + _ZIP64_EOCD_LEN <= len(data)
                and data[declared:declared + 4] == _ZIP64_EOCD_SIG
            ):
                zip64 = (
                    max(zip64[0], struct.unpack_from('<Q', data, declared + 32)[0]),
                    max(zip64[1], struct.unpack_from('<Q', data, declared + 40)[0]),
                )
    if zip64 is not None:
        entries, cd_size = zip64
    elif entries == 0xFFFF or cd_size == 0xFFFFFFFF:
        raise SafeZipError(REASON_INVALID_ARCHIVE)
    if entries > max_entries or cd_size > min(len(data), max_entries * _CD_BYTES_PER_ENTRY):
        raise SafeZipError(REASON_TOO_MANY_ENTRIES, str(max_entries))


def iter_safe_zip(
    data: bytes,
    *,
    max_files: Optional[int] = None,
    max_total_bytes: Optional[int] = None,
    max_file_bytes: Optional[int] = None,
    max_ratio: Optional[float] = None,
    max_archive_bytes: Optional[int] = None,
    require_skill_md: bool = True,
) -> Iterator[Tuple[str, bytes]]:
    """Validate a zip archive eagerly, then return an iterator of ``(normalised_name, content)``.

    All metadata checks (including, by default, the single-package-root check) run before this function
    returns, so a bad archive raises here, before any decompression. Decompression limits are enforced while
    iterating. Limits default to the ``SKILL_IMPORT_*`` settings. Directories and
    ``__MACOSX``/``.DS_Store``/``.git`` entries are skipped silently. A root-level ``SKILL.md`` is yielded as
    ``'SKILL.md'``. Prefer ``read_safe_zip`` for single-skill-package imports.

    Args:
        require_skill_md: When True (default), ``find_package_root`` is run and a package without exactly one
            resolvable ``SKILL.md`` root is rejected (the contract every existing caller relies on). Set to
            False for archives that intentionally hold more than one SKILL.md at different sub-paths (e.g. a
            multi-skill Claude Code plugin bundle) — callers doing so are responsible for locating/grouping
            each skill's own ``SKILL.md`` themselves; every other safety check (entry/size/ratio limits, path
            traversal, symlinks, encryption, duplicates) still applies unchanged.

    Raises:
        SafeZipError: On any violation, with a distinct ``reason``.
    """
    max_files = settings.SKILL_IMPORT_MAX_FILES if max_files is None else max_files
    max_total_bytes = settings.SKILL_IMPORT_MAX_TOTAL_BYTES if max_total_bytes is None else max_total_bytes
    max_file_bytes = settings.SKILL_IMPORT_MAX_FILE_BYTES if max_file_bytes is None else max_file_bytes
    max_ratio = settings.SKILL_IMPORT_MAX_RATIO if max_ratio is None else max_ratio
    max_archive_bytes = settings.SKILL_IMPORT_MAX_ARCHIVE_BYTES if max_archive_bytes is None else max_archive_bytes

    if len(data) > max_archive_bytes:
        raise SafeZipError(REASON_ARCHIVE_TOO_LARGE, str(max_archive_bytes))
    max_entries = max_files * _ENTRY_HARD_FACTOR
    _check_eocd(data, max_entries)

    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except Exception as exc:  # BadZipFile, EOFError, OSError, ValueError, struct.error, ...
        raise SafeZipError(REASON_INVALID_ARCHIVE) from exc

    try:
        entries = _check_entries(zf, max_entries, max_files, max_file_bytes, max_total_bytes)
        if require_skill_md:
            find_package_root([name for _, name in entries])
    except BaseException:
        zf.close()
        raise
    return _stream_entries(zf, entries, len(data), max_file_bytes, max_total_bytes, max_ratio)


def _check_entries(
    zf: zipfile.ZipFile,
    max_entries: int,
    max_files: int,
    max_file_bytes: int,
    max_total_bytes: int,
) -> List[Tuple[zipfile.ZipInfo, str]]:
    """Phase 1: metadata checks only (no decompression). Returns the surviving ``(info, name)`` pairs."""
    infos = zf.infolist()
    if len(infos) > max_entries:
        raise SafeZipError(REASON_TOO_MANY_ENTRIES, str(max_entries))
    entries: List[Tuple[zipfile.ZipInfo, str]] = []
    seen: Set[str] = set()
    header_total = 0
    for info in infos:
        _, segments = canonical_segments(info.filename)
        if info.is_dir() or info.filename.endswith('\\') or _is_junk(segments):
            continue
        if len(entries) + 1 > max_files:
            raise SafeZipError(REASON_TOO_MANY_FILES, str(max_files))
        if stat.S_ISLNK(info.external_attr >> 16):
            raise SafeZipError(REASON_SYMLINK, entry=info.filename)
        if info.flag_bits & 0x1:
            raise SafeZipError(REASON_ENCRYPTED, entry=info.filename)
        if info.compress_type not in _ALLOWED_COMPRESSION:
            raise SafeZipError(REASON_UNSUPPORTED_COMPRESSION, entry=info.filename)
        name = _validated_name(info.filename)
        key = name.lower()
        if key in seen:
            raise SafeZipError(REASON_DUPLICATE, entry=name)
        seen.add(key)
        # Cheap pre-checks only; the streamed count in phase 2 is authoritative.
        if info.file_size > max_file_bytes:
            raise SafeZipError(REASON_FILE_TOO_LARGE, str(max_file_bytes))
        header_total += info.file_size
        if header_total > max_total_bytes:
            raise SafeZipError(REASON_TOTAL_TOO_LARGE, str(max_total_bytes))
        entries.append((info, name))
    return entries


def _stream_entries(
    zf: zipfile.ZipFile,
    entries: List[Tuple[zipfile.ZipInfo, str]],
    archive_len: int,
    max_file_bytes: int,
    max_total_bytes: int,
    max_ratio: float,
) -> Iterator[Tuple[str, bytes]]:
    """Phase 2: stream each member in 64 KiB chunks, counting real bytes."""
    total_written = 0
    try:
        for info, name in entries:
            parts: List[bytes] = []
            file_written = 0
            try:
                with zf.open(info) as member:
                    while True:
                        chunk = member.read(_CHUNK_SIZE)
                        if not chunk:
                            break
                        file_written += len(chunk)
                        total_written += len(chunk)
                        if file_written > max_file_bytes:
                            raise SafeZipError(REASON_FILE_TOO_LARGE, str(max_file_bytes))
                        if total_written > max_total_bytes:
                            raise SafeZipError(REASON_TOTAL_TOO_LARGE, str(max_total_bytes))
                        # Authoritative ratio: real uploaded length (header compress_size is forgeable).
                        # Both checks only apply past the floor, see _RATIO_FLOOR_BYTES.
                        if total_written > _RATIO_FLOOR_BYTES and total_written / max(archive_len, 1) > max_ratio:
                            raise SafeZipError(REASON_RATIO, str(max_ratio))
                        # Extra defence for honest headers.
                        if file_written > _RATIO_FLOOR_BYTES and file_written / max(info.compress_size, 1) > max_ratio:
                            raise SafeZipError(REASON_RATIO, str(max_ratio))
                        parts.append(chunk)
            except SafeZipError:  # not dead: the generic handler below would otherwise swallow it
                raise
            except Exception as exc:  # BadZipFile, zlib/lzma errors, ValueError, MemoryError, OverflowError, ...
                raise SafeZipError(REASON_INVALID_ARCHIVE, entry=name) from exc
            yield name, b''.join(parts)
    finally:
        zf.close()


class SafeZipPackage(NamedTuple):
    """A validated skill package: the root SKILL.md bytes plus every other file by package-relative path."""

    skill_md: bytes
    files: Dict[str, bytes]


def read_safe_zip(data: bytes, **limits: object) -> SafeZipPackage:
    """Read a whole archive all-or-nothing into a ``SafeZipPackage``. Supported entry point for skill imports.

    Resolves the package root itself: ``skill_md`` is the root SKILL.md, and ``files`` maps stripped, normalised
    package-relative paths to content, excluding the root SKILL.md only (a nested ``references/SKILL.md`` is a
    normal file). Either everything passes every check or ``SafeZipError`` is raised and nothing is returned.
    ``**limits`` are the keyword limits of ``iter_safe_zip``.

    Raises:
        SafeZipError: On any violation.
    """
    entries = dict(iter_safe_zip(data, **limits))  # type: ignore[arg-type]
    root = find_package_root(list(entries))
    skill_md: Optional[bytes] = None
    files: Dict[str, bytes] = {}
    for name, content in entries.items():
        rel = strip_package_root(name, root)
        if rel is None:
            skill_md = content
        else:
            files[rel] = content
    if skill_md is None:  # unreachable: find_package_root guarantees it
        raise SafeZipError(REASON_NO_SKILL_MD)
    return SafeZipPackage(skill_md=skill_md, files=files)
