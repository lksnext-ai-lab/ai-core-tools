"""
Outbound skill-package archive builder for sandbox materialisation (FR-18, AD-5).

This is the second of the two archive modules referenced by AD-5:
- ``backend/utils/safe_zip.py`` is the **hardened inbound** zip reader used when
  a skill package is imported into Mattin AI.
- This module is the **outbound** builder used when a skill package already
  stored in the DB is pushed into a sandbox: it builds a single ``tar.gz`` (in
  memory) from a ``SkillPackagePayload`` plus the shell command that extracts it
  inside the sandbox.

Contains no ORM objects, no ``Session``, and does not import anything from
``backend/tools/sandbox/provider.py`` — ``extraction_command`` takes the
resolved sandbox-side root directory as an explicit argument instead of
importing ``SKILLS_ROOT`` from ``provider.py``, both to avoid a circular
import (``provider.py`` imports this module) and so each provider can supply
its own filesystem-root convention (see ``SandboxProvider.skills_root``).
"""

from __future__ import annotations

import gzip
import io
import posixpath
import shlex
import tarfile
from typing import TYPE_CHECKING

import config as settings

if TYPE_CHECKING:
    from schemas.skill_package_payload import SkillPackagePayload

# Pinned to the Unix epoch so the same payload always produces byte-identical
# tar.gz output (deterministic member order + fixed mtimes/ids/mode).
_FIXED_MTIME = 0


class SkillPackageTooLargeError(RuntimeError):
    """Raised by ``build_tar_gz`` when the payload's total byte size exceeds
    ``settings.SKILL_IMPORT_MAX_TOTAL_BYTES``.

    Deliberately a distinct type (not a bare ``ValueError``, which
    ``build_tar_gz`` already uses for path-safety rejections) so callers can
    tell a too-large-payload rejection apart from a path-traversal rejection
    and treat both as terminal (never fall back to a per-file writer that
    would just re-upload the same oversized payload without any cap check).
    """


def safe_member_name(path: str) -> str:
    """Normalise *path* to a safe, relative POSIX tar member name.

    Rejects absolute paths and any path that would escape the archive root —
    defence in depth on top of ``SkillPackageRepository.normalize_path``
    (which already enforced this when the file was imported): a provider-layer
    bug must not be able to trust stored data blindly.

    Public (no leading underscore) because more than one provider module
    (``provider.py``'s per-file fallback, ``opensandbox_provider.py``'s bulk
    write path) now calls this as a cross-module contract, not just this
    module's own ``build_tar_gz``.
    """
    posix_path = path.replace("\\", "/")
    normalized = posixpath.normpath(posix_path)
    if (
        not posix_path
        or posix_path.startswith("/")
        or normalized in ("..", ".")
        or normalized.startswith("../")
        or normalized.startswith("/")
    ):
        raise ValueError(f"skill_archive: refusing to package unsafe path: {path!r}")
    return normalized


def build_tar_gz(payload: "SkillPackagePayload") -> bytes:
    """Build a deterministic ``tar.gz`` of ``payload.files`` for sandbox upload.

    Determinism: files are written in the payload's own order but with a fixed
    mtime, mode, uid/gid and empty uname/gname on every member, and the gzip
    wrapper is written with ``mtime=0`` — so the exact same payload always
    yields byte-identical output regardless of when/where it is built. This
    makes the archive suitable for content-addressed caching later, though
    nothing in this feature relies on that yet.

    Security: every member is forced to ``tarfile.REGTYPE`` (a regular file) —
    ``payload.files`` only ever carries ``(path, bytes)`` tuples, so a symlink
    can never actually appear here, but pinning the type defensively ensures
    this function can never emit one even if a future caller starts passing
    filesystem-sourced entries. Absolute paths and path traversal are rejected
    via ``safe_member_name``.

    Size cap: the payload is already bounded at import time
    (``SKILL_IMPORT_MAX_TOTAL_BYTES``, enforced when the package first enters
    Mattin AI), but nothing re-checks that here and this function briefly
    holds the whole payload plus the in-memory archive (~2-3x the raw data),
    so a stale/tampered/corrupted DB row is re-validated against the same
    setting before any bytes are written to the archive buffer.
    """
    total_bytes = sum(len(data) for _, data in payload.files)
    if total_bytes > settings.SKILL_IMPORT_MAX_TOTAL_BYTES:
        raise SkillPackageTooLargeError(
            f"skill_archive: payload total size {total_bytes} bytes exceeds cap of "
            f"{settings.SKILL_IMPORT_MAX_TOTAL_BYTES} bytes"
        )
    buf = io.BytesIO()
    # tarfile.open's own "w:gz" mode has no way to pin the gzip header's mtime
    # field, which would otherwise make the output depend on wall-clock time.
    # Wrapping a GzipFile(mtime=0) ourselves keeps the whole output — gzip
    # header included — reproducible byte-for-byte for the same payload.
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=_FIXED_MTIME) as gz:
        with tarfile.open(fileobj=gz, mode="w") as tar:
            for path, data in payload.files:
                member_name = safe_member_name(path)
                info = tarfile.TarInfo(name=member_name)
                info.size = len(data)
                info.mtime = _FIXED_MTIME
                info.mode = 0o644
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                info.type = tarfile.REGTYPE
                tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def extraction_command(root: str, name: str) -> str:
    """Shell command that extracts ``<name>.tar.gz`` into ``<root>/<name>/``.

    *root* is the resolved sandbox-side skills root (see
    ``SandboxProvider.skills_root``); *name* is a normalised skill name
    (``payload.name``). Both are still defensively ``shlex.quote``-d here
    before being interpolated into the shell command string, since this
    command is executed via ``run_code``. Callers must never pass raw,
    unvalidated user input as *root* or *name*.

    The caller is responsible for verifying the command actually succeeded
    (``run_code`` returns an ``"[Error] ..."`` string on failure rather than
    raising) — see ``SandboxProvider._run_verified_command``.
    """
    archive_path = f"{root}/{name}.tar.gz"
    target_dir = f"{root}/{name}"
    quoted_archive = shlex.quote(archive_path)
    quoted_dir = shlex.quote(target_dir)
    return (
        f"mkdir -p {quoted_dir} && "
        f"tar -xzf {quoted_archive} -C {quoted_dir} && "
        f"rm -f {quoted_archive}"
    )
