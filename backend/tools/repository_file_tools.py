"""``get_repository_file``: lets an agent take a whole file from the repository behind its silo.

The retriever only returns chunks; some tasks need the original document (a template to fill in, a form, a
spreadsheet to process). This tool copies one repository file into the turn's workspace and returns its text,
exactly like a file the user uploaded, but without the user seeing it:

- ``destination="input"`` (default): ``<working_dir>/input/<name>``. Not listed in the conversation's files.
  When the turn has a sandbox it is also made available at ``input/<name>`` there (pushed when code first
  runs, without creating a sandbox just for this).
- ``destination="output"``: ``<working_dir>/output/<name>``. Registered at the end of the turn like any other
  deliverable, so the user sees it in the files panel and can download it.

Scope: only the repository that owns the agent's own silo (resolved at build time, never from the model's
input), and paths are resolved inside that repository's folder.
"""

from __future__ import annotations

import asyncio
import logging
import os
import posixpath
import shutil
from dataclasses import dataclass
from typing import Any, List, Literal, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from utils.path_safety import UnsafePathError, resolve_within

logger = logging.getLogger(__name__)

TOOL_NAME = "get_repository_file"
_INPUT_DIR = "input"
_OUTPUT_DIR = "output"
_MAX_LISTED = 50

Destination = Literal["input", "output"]


@dataclass(frozen=True)
class RepositoryFile:
    resource_id: int
    name: str
    path: str  # repository-relative, POSIX (folder path + uri)


class GetRepositoryFileInput(BaseModel):
    file: str = Field(
        description=(
            "The file to fetch: its `ref` or `name` from the search results' metadata "
            "(e.g. '12/templates/minutes.docx' or 'minutes.docx'), or its path inside the repository."
        )
    )
    destination: Destination = Field(
        default="input",
        description=(
            "'input' (default): working copy for you only, at input/<name>; the user does not see it. "
            "'output': the user gets it in their files panel to download."
        ),
    )


def repository_id_for_silo(silo: Any) -> Optional[int]:
    """Repository that owns ``silo`` (a REPO silo), or None. Lazy-loads: call off the event loop."""
    if silo is None:
        return None
    repository = getattr(silo, "repository", None)
    if isinstance(repository, (list, tuple)):
        repository = repository[0] if repository else None
    repository_id = getattr(repository, "repository_id", None)
    return repository_id if isinstance(repository_id, int) else None


def _list_repository_files(repository_id: int) -> List[RepositoryFile]:
    from db.database import SessionLocal
    from repositories.resource_repository import ResourceRepository

    db = SessionLocal()
    try:
        folder_paths: dict[int, str] = {}
        files: List[RepositoryFile] = []
        for resource in ResourceRepository.get_by_repository_id(db, repository_id):
            if not resource.uri:
                continue
            folder_path = ""
            if resource.folder_id:
                if resource.folder_id not in folder_paths:
                    folder = resource.folder
                    folder_paths[resource.folder_id] = folder.get_path() if folder is not None else ""
                folder_path = folder_paths[resource.folder_id]
            files.append(
                RepositoryFile(
                    resource_id=resource.resource_id,
                    name=resource.name or resource.uri,
                    path=posixpath.join(folder_path, resource.uri) if folder_path else resource.uri,
                )
            )
        return files
    finally:
        db.close()


def _match(files: List[RepositoryFile], query: str, repository_id: int) -> tuple[Optional[RepositoryFile], List[RepositoryFile]]:
    """``(file, [])`` on a single match, ``(None, candidates)`` when ambiguous, ``(None, [])`` when none."""
    wanted = query.strip().replace("\\", "/").lstrip("/")
    prefix = f"{repository_id}/"
    if wanted.startswith(prefix):  # a metadata `ref` is "<repository_id>/<path>"
        wanted = wanted[len(prefix):]
    if not wanted:
        return None, []

    for same in (lambda a, b: a == b, lambda a, b: a.casefold() == b.casefold()):
        hits = [f for f in files if same(f.path, wanted)]
        if len(hits) == 1:
            return hits[0], []

    base = posixpath.basename(wanted).casefold()
    hits = [
        f for f in files
        if posixpath.basename(f.path).casefold() == base or f.name.casefold() == wanted.casefold()
    ]
    if len(hits) == 1:
        return hits[0], []
    return None, hits


def _available_list(files: List[RepositoryFile]) -> str:
    listed = ", ".join(f.path for f in files[:_MAX_LISTED])
    more = f" (and {len(files) - _MAX_LISTED} more)" if len(files) > _MAX_LISTED else ""
    return listed + more


def create_repository_file_tool(
    repository_id: int,
    working_dir: str,
    sandbox_handle: Optional[Any] = None,
) -> StructuredTool:
    """Build ``get_repository_file`` bound to one repository and one turn's workspace.

    ``sandbox_handle`` is the turn's lazy sandbox handle (or None when there is no code interpreter): input
    files are staged on it with ``stage_input_file`` so they reach the sandbox's ``input/`` too.
    """

    def get_repository_file(file: str, destination: Destination = "input") -> str:
        from services.file_management_service import extract_text_from_path
        from services.repository_service import REPO_BASE_FOLDER

        try:
            files = _list_repository_files(repository_id)
        except Exception as exc:
            logger.warning("get_repository_file: could not list repository %s: %s", repository_id, exc)
            return "[Error] The repository could not be read."

        found, candidates = _match(files, file or "", repository_id)
        if found is None:
            if candidates:
                return (
                    f"[Error] '{file}' matches several files; ask again with the full path. "
                    f"Candidates: {_available_list(candidates)}"
                )
            if not files:
                return "[Error] The repository has no files."
            return f"[Error] No file '{file}' in the repository. Available files: {_available_list(files)}"

        try:
            source = resolve_within(os.path.join(REPO_BASE_FOLDER, str(repository_id)), found.path)
        except UnsafePathError:
            logger.warning("get_repository_file: unsafe path for resource %s", found.resource_id)
            return "[Error] The file could not be read."
        if not os.path.isfile(source):
            logger.warning("get_repository_file: resource %s has no file on disk", found.resource_id)
            return f"[Error] The file '{found.path}' is listed but missing from storage."

        filename = posixpath.basename(found.path)
        dest_dir = _OUTPUT_DIR if destination == "output" else _INPUT_DIR
        try:
            target = resolve_within(working_dir, dest_dir, filename)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(source, target)
        except (OSError, UnsafePathError) as exc:
            logger.warning("get_repository_file: could not copy resource %s: %s", found.resource_id, exc)
            return "[Error] The file could not be copied to the workspace."

        workspace_path = f"{dest_dir}/{filename}"
        notes = []
        if destination == "output":
            notes.append(f"Copied to {workspace_path}; the user will get it in their files panel to download.")
        else:
            notes.append(f"Copied to {workspace_path} (working copy, not shown to the user).")
            if sandbox_handle is not None and hasattr(sandbox_handle, "stage_input_file"):
                if sandbox_handle.stage_input_file(filename, target):
                    notes.append(f"Code interpreter path: {workspace_path}.")
                else:
                    notes.append("It could not be copied into the code interpreter sandbox.")

        try:
            text = extract_text_from_path(target, filename)
        except Exception as exc:
            logger.warning("get_repository_file: text extraction failed for resource %s: %s", found.resource_id, exc)
            text = None
            notes.append("Its text could not be extracted.")
        else:
            if text is None:
                notes.append("There is no text extraction for this file type.")

        logger.info(
            "get_repository_file: resource %s of repository %s -> %s", found.resource_id, repository_id, workspace_path
        )
        header = f"Repository file '{found.path}'. " + " ".join(notes)
        if text is None:
            return header
        return f"{header}\n\n--- Content of {filename} ---\n{text}\n--- End of {filename} ---"

    return StructuredTool.from_function(
        func=get_repository_file,
        name=TOOL_NAME,
        description=(
            "Fetch a whole file from the document repository behind your knowledge base and return its text. "
            "Use it when you need an entire document rather than search passages, e.g. a template to fill in. "
            "Identify the file by the `ref` or `name` in the search results' metadata, or by its name. "
            "By default the copy is for you only (input/<name>, also available to the code interpreter); "
            "use destination='output' only when the user should be able to download the file itself."
        ),
        args_schema=GetRepositoryFileInput,
    )


async def build_repository_file_tool(agent: Any, working_dir: str, sandbox_handle: Optional[Any] = None) -> Optional[StructuredTool]:
    """The tool for ``agent`` when its silo is backed by a repository, else None. Never raises."""
    if getattr(agent, "silo_id", None) is None:
        return None
    try:
        repository_id = await asyncio.to_thread(lambda: repository_id_for_silo(agent.silo))
    except Exception as exc:  # an optional tool must never fail the turn
        logger.warning("Could not resolve the repository of agent %s's silo: %s", getattr(agent, "agent_id", None), exc)
        return None
    if repository_id is None:
        return None
    return create_repository_file_tool(repository_id, working_dir, sandbox_handle=sandbox_handle)
