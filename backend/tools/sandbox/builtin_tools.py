"""Claude-style builtin tools backed by a Linux sandbox.

The tools in this module intentionally use ordinary Linux commands inside the
sandbox instead of backend filesystem access.  That keeps their view aligned
with the agent's execution environment across E2B, OpenSandbox, Daytona, and
local subprocess sandboxes.
"""

from __future__ import annotations

import base64
import json
import re
import shlex
import uuid
from dataclasses import dataclass
from typing import Any, Literal

import config as settings
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field
from utils.logger import get_logger

from .provider import SandboxExpiredError, SandboxHandle, SandboxProvider

logger = get_logger(__name__)


@dataclass
class _SandboxHandleRef:
    """Mutable holder for a ``SandboxHandle``.

    All builtin tools created by a single ``create_sandbox_builtin_tools`` call
    share one instance of this holder (captured by closure). When a sandbox
    session expires mid-turn, ``_run_bash_with_recovery`` can swap in a freshly
    recreated handle here and every tool immediately sees the new handle on its
    next call — without each tool closure needing to hold its own reference.
    """

    handle: SandboxHandle


_BG_SHELLS_KEY = "_mattin_builtin_background_shells"
_DEFAULT_READ_LIMIT = 2000
_MAX_READ_LINE_CHARS = 2000
_BASH_OUTPUT_LIMIT = 30_000
_BASH_DEFAULT_TIMEOUT_S = 120
_BASH_MAX_TIMEOUT_S = 600


class SandboxInfoArgs(BaseModel):
    pass


class PWDArgs(BaseModel):
    pass


class ReadArgs(BaseModel):
    file_path: str = Field(description="The absolute path to the file to read")
    offset: int | None = Field(
        default=None,
        description="The line number to start reading from. Defaults to 1.",
    )
    limit: int | None = Field(
        default=None,
        description="The number of lines to read. Defaults to 2000.",
    )


class WriteArgs(BaseModel):
    file_path: str = Field(
        description="The absolute path to the file to write (must be absolute)"
    )
    content: str = Field(description="The complete file content")


class EditArgs(BaseModel):
    file_path: str = Field(description="The absolute path to the file to modify")
    old_string: str = Field(description="The exact text to replace")
    new_string: str = Field(description="The replacement text")
    replace_all: bool = Field(
        default=False,
        description="Replace all occurrences of old_string. Defaults to false.",
    )


class GlobArgs(BaseModel):
    pattern: str = Field(description="The glob pattern to match files against")
    path: str | None = Field(
        default=None,
        description="Directory to search in. Defaults to the sandbox working directory.",
    )


class LSArgs(BaseModel):
    path: str | None = Field(
        default=None,
        description="Directory or file to list inside the sandbox. Defaults to the current working directory.",
    )
    show_hidden: bool = Field(
        default=False,
        description="Include dotfiles and hidden entries. Defaults to false.",
    )
    limit: int | None = Field(
        default=None,
        description="Maximum entries to return. Defaults to 200, maximum 1000.",
    )


class GrepArgs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    pattern: str = Field(description="The regular expression pattern to search for")
    path: str | None = Field(
        default=None,
        description="File or directory to search in. Defaults to the current working directory.",
    )
    output_mode: Literal["content", "files_with_matches", "count"] = Field(
        default="files_with_matches",
        description="Output mode. Defaults to files_with_matches.",
    )
    glob: str | None = Field(default=None, description="Glob pattern to filter files")
    type: str | None = Field(default=None, description="Ripgrep file type, e.g. py, js")
    case_insensitive: bool = Field(
        default=False,
        alias="-i",
        description="Case-insensitive search",
    )
    line_numbers: bool = Field(
        default=False,
        alias="-n",
        description="Show line numbers for content output",
    )
    after_context: int | None = Field(default=None, alias="-A")
    before_context: int | None = Field(default=None, alias="-B")
    context: int | None = Field(default=None, alias="-C")
    multiline: bool = Field(default=False, description="Enable multiline mode")
    head_limit: int | None = Field(default=None, description="Limit returned entries")


class StatArgs(BaseModel):
    path: str = Field(description="File or directory path inside the sandbox")


class BashArgs(BaseModel):
    command: str = Field(description="The bash command to execute")
    description: str | None = Field(
        default=None,
        description="Clear, concise description of what this command does",
    )
    timeout: int | None = Field(
        default=None,
        description="Optional timeout in milliseconds, maximum 600000",
    )
    run_in_background: bool = Field(
        default=False,
        description="Run this command in the background and use BashOutput later",
    )


class BashOutputArgs(BaseModel):
    bash_id: str = Field(description="The ID of the background shell")
    filter: str | None = Field(
        default=None,
        description="Optional regex used to include matching output lines only",
    )


class KillShellArgs(BaseModel):
    shell_id: str = Field(description="The ID of the background shell to kill")


def _supports_bash(provider: SandboxProvider) -> bool:
    try:
        return "bash" in provider.get_supported_languages()
    except Exception:
        return False


def _require_bash(provider: SandboxProvider) -> str | None:
    if _supports_bash(provider):
        return None
    return (
        "[Error] These builtin tools require a Linux sandbox with bash support. "
        f"Available languages: {provider.get_supported_languages()}"
    )


def _run_bash(
    provider: SandboxProvider,
    handle: SandboxHandle,
    command: str,
    *,
    timeout: int | None = None,
    max_output_chars: int | None = None,
) -> str:
    missing = _require_bash(provider)
    if missing is not None:
        return missing
    try:
        return provider.run_code(
            handle,
            command,
            language="bash",
            timeout=timeout,
            max_output_chars=max_output_chars,
        )
    except SandboxExpiredError:
        raise
    except Exception as exc:
        return f"[Error] Sandbox command failed: {exc}"


_SANDBOX_EXPIRED_MESSAGE = (
    "[Error] Sandbox session expired and was reset. Please retry the code execution."
)


def _recreate_stale_handle(
    handle_ref: _SandboxHandleRef,
    provider: SandboxProvider,
    *,
    session_key: str | None,
    session_service: Any | None,
) -> bool:
    """Evict the stale cached session and swap in a freshly created handle.

    Mirrors ``tool_factory.py``'s ``_recreate_stale_handle`` so builtin tools and
    REPL tools recover from an expired sandbox the same way.
    """
    if session_service is None or session_key is None:
        return False
    try:
        session_service.evict(session_key)
        handle_ref.handle = session_service.get_or_create(
            session_key,
            provider,
            handle_ref.handle.working_dir,
        )
        logger.info(
            "Recovered sandbox session %s with new sandbox_id=%s",
            session_key,
            handle_ref.handle.sandbox_id,
        )
        return True
    except Exception as exc:
        logger.warning(
            "Failed to recreate sandbox session %s after expiry: %s",
            session_key,
            exc,
            exc_info=True,
        )
        return False


def _run_bash_with_recovery(
    provider: SandboxProvider,
    handle_ref: _SandboxHandleRef,
    command: str,
    *,
    session_key: str | None = None,
    session_service: Any | None = None,
    timeout: int | None = None,
    max_output_chars: int | None = None,
) -> str:
    """Run *command* via ``_run_bash``, recovering once from a stale sandbox.

    On ``SandboxExpiredError`` this attempts to evict the cached session and
    obtain a fresh handle (updating *handle_ref* in place) and retries the
    command exactly once. If recovery isn't possible (no session service/key)
    or the retried attempt also raises ``SandboxExpiredError``, a clean
    user-facing error string is returned instead of letting the exception
    propagate and crash the agent turn.
    """
    for attempt in range(2):
        try:
            return _run_bash(
                provider,
                handle_ref.handle,
                command,
                timeout=timeout,
                max_output_chars=max_output_chars,
            )
        except SandboxExpiredError:
            if attempt == 0 and _recreate_stale_handle(
                handle_ref,
                provider,
                session_key=session_key,
                session_service=session_service,
            ):
                continue
            return _SANDBOX_EXPIRED_MESSAGE
    return _SANDBOX_EXPIRED_MESSAGE


def _abs_path_error(path: str) -> str | None:
    if not path or not path.startswith("/"):
        # Actionable, not just a rejection: the absolute workspace root
        # differs per provider (e.g. OpenSandbox mounts at `/workspace`,
        # Daytona's default workspace lives under the sandbox user's home
        # directory instead) and nothing else tells the model this before
        # its first file-tool call. Without a next step here, models were
        # observed guessing several wrong absolute prefixes in a row before
        # giving up (or looping indefinitely) instead of just asking the
        # sandbox directly.
        return (
            "[Error] Path must be absolute inside the sandbox. "
            "Call PWD (or SandboxInfo) first to get the sandbox's actual "
            "working directory, then build the absolute path from that — "
            "do not guess a prefix like /workspace."
        )
    return None


def _sh(path: str) -> str:
    return shlex.quote(path)


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _python_payload(script: str) -> str:
    encoded = _b64(script)
    return (
        "if command -v python3 >/dev/null 2>&1; then py=python3; "
        "elif command -v python >/dev/null 2>&1; then py=python; "
        "else echo '[Error] python3 or python is required for this tool'; exit 0; fi; "
        f"$py -c \"$(printf %s {shlex.quote(encoded)} | base64 -d)\""
    )


def _path_exists(
    provider: SandboxProvider,
    handle_ref: _SandboxHandleRef,
    file_path: str,
    *,
    session_key: str | None = None,
    session_service: Any | None = None,
) -> bool:
    result = _run_bash_with_recovery(
        provider,
        handle_ref,
        f"if [ -e {_sh(file_path)} ]; then echo __mattin_exists__; fi",
        session_key=session_key,
        session_service=session_service,
        timeout=5,
        max_output_chars=1000,
    )
    return "__mattin_exists__" in result


def _sandbox_info_tool(
    provider: SandboxProvider,
    handle_ref: _SandboxHandleRef,
    *,
    session_key: str | None = None,
    session_service: Any | None = None,
):
    def SandboxInfo() -> str:
        """Sandbox-only operation: summarize actionable sandbox workspace rules, tools, and limits."""
        languages = ", ".join(provider.get_supported_languages())
        tools = (
            "SandboxInfo, PWD, Read, Write, Edit, LS, Stat, Glob, Grep, "
            "Bash, BashOutput, KillShell"
        )
        quoted_languages = shlex.quote(languages)
        quoted_tools = shlex.quote(tools)
        quoted_read_limit = shlex.quote(str(_DEFAULT_READ_LIMIT))
        quoted_max_line = shlex.quote(str(_MAX_READ_LINE_CHARS))
        quoted_ls_default = shlex.quote("200")
        quoted_ls_max = shlex.quote("1000")
        quoted_bash_default = shlex.quote(str(_BASH_DEFAULT_TIMEOUT_S))
        quoted_bash_max = shlex.quote(str(_BASH_MAX_TIMEOUT_S))
        quoted_bash_output = shlex.quote(str(_BASH_OUTPUT_LIMIT))
        quoted_tool_output = shlex.quote(str(settings.SANDBOX_MAX_OUTPUT_CHARS))
        command = (
            "printf 'sandbox\tlinux\\n'; "
            "printf 'cwd\t'; pwd; "
            f"printf 'runtimes\t%s\\n' {quoted_languages}; "
            f"printf 'builtin_tools\t%s\\n' {quoted_tools}; "
            "printf 'dirs\\n'; "
            "for d in input work output; do "
            "[ -d \"$d\" ] && exists=yes || exists=no; "
            "case \"$d\" in "
            "input) desc='user uploads/source files' ;; "
            "work) desc='scratch/intermediate files' ;; "
            "output) desc='final user-facing deliverables' ;; "
            "esac; "
            "printf '%s\\t%s\\t%s\\n' \"$d\" \"$exists\" \"$desc\"; "
            "done; "
            "printf 'paths\\n'; "
            "printf 'file_tools_require\\tabsolute sandbox paths\\n'; "
            "printf 'relative_paths_from\\tcwd\\n'; "
            "printf 'rules\\n'; "
            "printf 'all_operations\\tsandbox-only\\n'; "
            "printf 'existing_files\\tRead before Edit or overwrite with Write\\n'; "
            "printf 'large_output\\twrite to work/ or output/, then inspect chunks\\n'; "
            "printf 'limits\\n'; "
            f"printf 'Read\\tdefault=%s_lines max_line=%s_chars action=use_offset_limit\\n' {quoted_read_limit} {quoted_max_line}; "
            f"printf 'LS\\tdefault=%s_entries max=%s action=filter_or_descend\\n' {quoted_ls_default} {quoted_ls_max}; "
            f"printf 'Bash\\tdefault_timeout=%ss max_timeout=%ss action=background_for_long_tasks\\n' {quoted_bash_default} {quoted_bash_max}; "
            f"printf 'BashOutput\\tmax=%s_chars action=redirect_large_output_to_file\\n' {quoted_bash_output}; "
            f"printf 'tool_output\\tmax=%s_chars action=write_large_results_to_files\\n' {quoted_tool_output}"
        )
        return _run_bash_with_recovery(
            provider,
            handle_ref,
            command,
            session_key=session_key,
            session_service=session_service,
            timeout=5,
            max_output_chars=4000,
        )

    return StructuredTool.from_function(
        func=SandboxInfo,
        name="SandboxInfo",
        description=SandboxInfo.__doc__ or "",
        args_schema=SandboxInfoArgs,
    )


def _pwd_tool(
    provider: SandboxProvider,
    handle_ref: _SandboxHandleRef,
    *,
    session_key: str | None = None,
    session_service: Any | None = None,
):
    def PWD() -> str:
        """Sandbox-only operation: print the current working directory inside the sandbox."""
        return _run_bash_with_recovery(
            provider,
            handle_ref,
            "pwd",
            session_key=session_key,
            session_service=session_service,
            timeout=5,
            max_output_chars=1000,
        )

    return StructuredTool.from_function(
        func=PWD,
        name="PWD",
        description=PWD.__doc__ or "",
        args_schema=PWDArgs,
    )


def _read_tool(
    provider: SandboxProvider,
    handle_ref: _SandboxHandleRef,
    read_files: set[str],
    *,
    session_key: str | None = None,
    session_service: Any | None = None,
):
    def Read(file_path: str, offset: int | None = None, limit: int | None = None) -> str:
        """Sandbox-only operation: read file contents from the sandbox filesystem with line numbers."""
        if err := _abs_path_error(file_path):
            return err
        start = max(1, int(offset or 1))
        count = max(1, int(limit or _DEFAULT_READ_LIMIT))
        end = start + count
        script = (
            f"p={_sh(file_path)}; "
            "if [ ! -e \"$p\" ]; then echo \"[Error] File not found: $p\"; exit 0; fi; "
            "if [ -d \"$p\" ]; then echo \"[Error] Path is a directory. Use Bash ls for directories.\"; exit 0; fi; "
            "if [ ! -s \"$p\" ]; then echo \"[System reminder: file is empty]\"; exit 0; fi; "
            f"awk 'NR>={start} && NR<{end} {{ line=$0; "
            f"if (length(line)>{_MAX_READ_LINE_CHARS}) line=substr(line,1,{_MAX_READ_LINE_CHARS})\"...\"; "
            "printf \"%6d\\t%s\\n\", NR, line }' \"$p\""
        )
        output = _run_bash_with_recovery(
            provider,
            handle_ref,
            script,
            session_key=session_key,
            session_service=session_service,
            max_output_chars=settings.SANDBOX_MAX_OUTPUT_CHARS,
        )
        if "[Error]" not in output:
            read_files.add(file_path)
        return output

    return StructuredTool.from_function(
        func=Read,
        name="Read",
        description=Read.__doc__ or "",
        args_schema=ReadArgs,
    )


def _write_tool(
    provider: SandboxProvider,
    handle_ref: _SandboxHandleRef,
    read_files: set[str],
    *,
    session_key: str | None = None,
    session_service: Any | None = None,
):
    def Write(file_path: str, content: str) -> str:
        """Sandbox-only operation: create or completely overwrite a file in the sandbox filesystem."""
        if err := _abs_path_error(file_path):
            return err
        if file_path not in read_files and _path_exists(
            provider,
            handle_ref,
            file_path,
            session_key=session_key,
            session_service=session_service,
        ):
            return (
                "[Error] Existing files must be read with Read before Write can "
                "overwrite them."
            )
        encoded = _b64(content)
        script = (
            f"p={_sh(file_path)}; "
            f"if [ -e \"$p\" ] && [ ! -f \"$p\" ]; then echo '[Error] Existing path is not a regular file'; exit 0; fi; "
            f"mkdir -p \"$(dirname \"$p\")\" && printf %s {shlex.quote(encoded)} | base64 -d > \"$p\" && "
            "printf 'Wrote %s bytes to %s\\n' \"$(wc -c < \"$p\")\" \"$p\""
        )
        return _run_bash_with_recovery(
            provider,
            handle_ref,
            script,
            session_key=session_key,
            session_service=session_service,
        )

    return StructuredTool.from_function(
        func=Write,
        name="Write",
        description=(Write.__doc__ or "")
        + "\n\nPrefer Edit for existing files. Read existing files before overwriting when possible.",
        args_schema=WriteArgs,
    )


def _edit_tool(
    provider: SandboxProvider,
    handle_ref: _SandboxHandleRef,
    read_files: set[str],
    *,
    session_key: str | None = None,
    session_service: Any | None = None,
):
    def Edit(
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> str:
        """Sandbox-only operation: replace exact text in a sandbox file."""
        if err := _abs_path_error(file_path):
            return err
        if file_path not in read_files:
            return "[Error] Files must be read with Read before Edit can modify them."
        if old_string == new_string:
            return "[Error] new_string must be different from old_string."
        payload = {
            "file_path": file_path,
            "old_string": old_string,
            "new_string": new_string,
            "replace_all": replace_all,
        }
        script = r"""
import json
import os
import sys

payload = json.loads(os.environ["MATTIN_EDIT_PAYLOAD"])
path = payload["file_path"]
old = payload["old_string"]
new = payload["new_string"]
replace_all = bool(payload.get("replace_all"))

try:
    with open(path, "r", encoding="utf-8", newline="") as fh:
        text = fh.read()
except FileNotFoundError:
    print(f"[Error] File not found: {path}")
    sys.exit(0)
except IsADirectoryError:
    print("[Error] Path is a directory.")
    sys.exit(0)

count = text.count(old)
if count == 0:
    print("[Error] old_string not found.")
    sys.exit(0)
if not replace_all and count != 1:
    print(f"[Error] old_string appears {count} times. Use replace_all=true or provide a unique string.")
    sys.exit(0)

updated = text.replace(old, new) if replace_all else text.replace(old, new, 1)
tmp = path + ".mattin-edit-tmp"
with open(tmp, "w", encoding="utf-8", newline="") as fh:
    fh.write(updated)
os.replace(tmp, path)
print(f"Replaced {count if replace_all else 1} occurrence(s) in {path}.")
"""
        command = (
            f"export MATTIN_EDIT_PAYLOAD={shlex.quote(json.dumps(payload))}; "
            + _python_payload(script)
        )
        return _run_bash_with_recovery(
            provider,
            handle_ref,
            command,
            session_key=session_key,
            session_service=session_service,
        )

    return StructuredTool.from_function(
        func=Edit,
        name="Edit",
        description=Edit.__doc__ or "",
        args_schema=EditArgs,
    )


def _glob_tool(
    provider: SandboxProvider,
    handle_ref: _SandboxHandleRef,
    *,
    session_key: str | None = None,
    session_service: Any | None = None,
):
    def Glob(pattern: str, path: str | None = None) -> str:
        """Sandbox-only operation: find files by glob pattern in the sandbox, sorted by modification time newest first."""
        root = path or "."
        script = r"""
import glob
import os
import sys

root = os.environ.get("MATTIN_GLOB_ROOT") or "."
pattern = os.environ["MATTIN_GLOB_PATTERN"]
if root in ("undefined", "null"):
    root = "."
if not os.path.isdir(root):
    print(f"[Error] Not a directory: {root}")
    sys.exit(0)
full_pattern = pattern if os.path.isabs(pattern) else os.path.join(root, pattern)
matches = [p for p in glob.glob(full_pattern, recursive=True) if os.path.isfile(p)]
matches.sort(key=lambda p: os.path.getmtime(p), reverse=True)
print("\n".join(matches))
"""
        command = (
            f"export MATTIN_GLOB_ROOT={shlex.quote(root)}; "
            f"export MATTIN_GLOB_PATTERN={shlex.quote(pattern)}; "
            + _python_payload(script)
        )
        return _run_bash_with_recovery(
            provider,
            handle_ref,
            command,
            session_key=session_key,
            session_service=session_service,
        )

    return StructuredTool.from_function(
        func=Glob,
        name="Glob",
        description=Glob.__doc__ or "",
        args_schema=GlobArgs,
    )


def _ls_tool(
    provider: SandboxProvider,
    handle_ref: _SandboxHandleRef,
    *,
    session_key: str | None = None,
    session_service: Any | None = None,
):
    def LS(path: str | None = None, show_hidden: bool = False, limit: int | None = None) -> str:
        """Sandbox-only operation: list sandbox directory entries in a compact token-efficient format."""
        capped_limit = max(1, min(1000, int(limit or 200)))
        target = path or "."
        script = r"""
import json
import os
import stat
import sys

payload = json.loads(os.environ["MATTIN_LS_PAYLOAD"])
target = payload["path"]
show_hidden = bool(payload.get("show_hidden"))
limit = int(payload.get("limit") or 200)

def kind(mode):
    if stat.S_ISDIR(mode):
        return "d"
    if stat.S_ISLNK(mode):
        return "l"
    if stat.S_ISREG(mode):
        return "f"
    return "o"

def compact_size(size):
    if size < 1024:
        return str(size)
    units = ("K", "M", "G", "T")
    value = float(size)
    for unit in units:
        value /= 1024.0
        if value < 1024:
            return f"{value:.1f}{unit}".rstrip("0").rstrip(".")
    return f"{value:.1f}P".rstrip("0").rstrip(".")

try:
    st = os.lstat(target)
except FileNotFoundError:
    print(f"[Error] Path not found: {target}")
    sys.exit(0)

if not stat.S_ISDIR(st.st_mode):
    name = os.path.basename(target.rstrip(os.sep)) or target
    suffix = "/" if stat.S_ISDIR(st.st_mode) else "@" if stat.S_ISLNK(st.st_mode) else ""
    print(target)
    print(f"{kind(st.st_mode)}\t{compact_size(st.st_size)}\t{name}{suffix}")
    sys.exit(0)

try:
    entries = list(os.scandir(target))
except PermissionError:
    print(f"[Error] Permission denied: {target}")
    sys.exit(0)

if not show_hidden:
    entries = [entry for entry in entries if not entry.name.startswith(".")]

def sort_key(entry):
    try:
        entry_mode = entry.stat(follow_symlinks=False).st_mode
        is_dir = stat.S_ISDIR(entry_mode)
    except OSError:
        is_dir = False
    return (0 if is_dir else 1, entry.name.lower())

entries.sort(key=sort_key)
total = len(entries)
shown = entries[:limit]

print(os.path.abspath(target))
for entry in shown:
    try:
        entry_stat = entry.stat(follow_symlinks=False)
        entry_kind = kind(entry_stat.st_mode)
        size = "-" if entry_kind == "d" else compact_size(entry_stat.st_size)
        suffix = "/" if entry_kind == "d" else "@" if entry_kind == "l" else ""
        print(f"{entry_kind}\t{size}\t{entry.name}{suffix}")
    except OSError as exc:
        print(f"?\t-\t{entry.name}\t{exc.__class__.__name__}")

if total > limit:
    print(f"... {total - limit} more")
"""
        payload = {
            "path": target,
            "show_hidden": show_hidden,
            "limit": capped_limit,
        }
        command = (
            f"export MATTIN_LS_PAYLOAD={shlex.quote(json.dumps(payload))}; "
            + _python_payload(script)
        )
        return _run_bash_with_recovery(
            provider,
            handle_ref,
            command,
            session_key=session_key,
            session_service=session_service,
            timeout=10,
            max_output_chars=settings.SANDBOX_MAX_OUTPUT_CHARS,
        )

    return StructuredTool.from_function(
        func=LS,
        name="LS",
        description=LS.__doc__ or "",
        args_schema=LSArgs,
    )


def _grep_tool(
    provider: SandboxProvider,
    handle_ref: _SandboxHandleRef,
    *,
    session_key: str | None = None,
    session_service: Any | None = None,
):
    def Grep(
        pattern: str,
        path: str | None = None,
        output_mode: str = "files_with_matches",
        glob: str | None = None,
        type: str | None = None,
        case_insensitive: bool = False,
        line_numbers: bool = False,
        after_context: int | None = None,
        before_context: int | None = None,
        context: int | None = None,
        multiline: bool = False,
        head_limit: int | None = None,
    ) -> str:
        """Sandbox-only operation: search sandbox file contents, preferring ripgrep when present."""
        if output_mode not in {"content", "files_with_matches", "count"}:
            return "[Error] output_mode must be content, files_with_matches, or count."
        target = path or "."
        args = ["rg", "--color", "never"]
        if output_mode == "files_with_matches":
            args.append("--files-with-matches")
        elif output_mode == "count":
            args.append("--count")
        else:
            if line_numbers:
                args.append("-n")
            if after_context is not None:
                args.extend(["-A", str(max(0, int(after_context)))])
            if before_context is not None:
                args.extend(["-B", str(max(0, int(before_context)))])
            if context is not None:
                args.extend(["-C", str(max(0, int(context)))])
        if case_insensitive:
            args.append("-i")
        if glob:
            args.extend(["--glob", glob])
        if type:
            args.extend(["--type", type])
        if multiline:
            args.extend(["-U", "--multiline-dotall"])
        args.extend([pattern, target])
        rg_cmd = " ".join(shlex.quote(a) for a in args)

        fallback = _grep_fallback_command(
            pattern=pattern,
            target=target,
            output_mode=output_mode,
            glob=glob,
            case_insensitive=case_insensitive,
            line_numbers=line_numbers,
            head_limit=head_limit,
        )
        command = f"if command -v rg >/dev/null 2>&1; then {rg_cmd}; else {fallback}; fi"
        if head_limit is not None:
            command = f"{command} | head -n {shlex.quote(str(max(1, int(head_limit))))}"
        return _run_bash_with_recovery(
            provider,
            handle_ref,
            command,
            session_key=session_key,
            session_service=session_service,
            max_output_chars=settings.SANDBOX_MAX_OUTPUT_CHARS,
        )

    return StructuredTool.from_function(
        func=Grep,
        name="Grep",
        description=Grep.__doc__ or "",
        args_schema=GrepArgs,
    )


def _grep_fallback_command(
    *,
    pattern: str,
    target: str,
    output_mode: str,
    glob: str | None,
    case_insensitive: bool,
    line_numbers: bool,
    head_limit: int | None,
) -> str:
    """Return a python-based grep fallback for sandboxes without ripgrep."""
    script = r"""
import fnmatch
import os
import re
import sys

pattern = os.environ["MATTIN_GREP_PATTERN"]
target = os.environ.get("MATTIN_GREP_TARGET") or "."
mode = os.environ.get("MATTIN_GREP_MODE") or "files_with_matches"
glob_pat = os.environ.get("MATTIN_GREP_GLOB") or ""
flags = re.IGNORECASE if os.environ.get("MATTIN_GREP_I") == "1" else 0
line_numbers = os.environ.get("MATTIN_GREP_N") == "1"
try:
    rx = re.compile(pattern, flags)
except re.error as exc:
    print(f"[Error] Invalid regex: {exc}")
    sys.exit(0)

def iter_files(root):
    if os.path.isfile(root):
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        if ".git" in dirnames:
            dirnames.remove(".git")
        for name in filenames:
            path = os.path.join(dirpath, name)
            if glob_pat and not fnmatch.fnmatch(path, glob_pat) and not fnmatch.fnmatch(name, glob_pat):
                continue
            yield path

for path in iter_files(target):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            lines = fh.readlines()
    except Exception:
        continue
    matched = []
    for idx, line in enumerate(lines, start=1):
        if rx.search(line):
            matched.append((idx, line.rstrip("\n")))
    if not matched:
        continue
    if mode == "files_with_matches":
        print(path)
    elif mode == "count":
        print(f"{path}:{len(matched)}")
    else:
        for idx, line in matched:
            prefix = f"{path}:{idx}:" if line_numbers else f"{path}:"
            print(prefix + line)
"""
    return (
        f"export MATTIN_GREP_PATTERN={shlex.quote(pattern)}; "
        f"export MATTIN_GREP_TARGET={shlex.quote(target)}; "
        f"export MATTIN_GREP_MODE={shlex.quote(output_mode)}; "
        f"export MATTIN_GREP_GLOB={shlex.quote(glob or '')}; "
        f"export MATTIN_GREP_I={'1' if case_insensitive else '0'}; "
        f"export MATTIN_GREP_N={'1' if line_numbers else '0'}; "
        + _python_payload(script)
    )


def _stat_tool(
    provider: SandboxProvider,
    handle_ref: _SandboxHandleRef,
    *,
    session_key: str | None = None,
    session_service: Any | None = None,
):
    def Stat(path: str) -> str:
        """Sandbox-only operation: return compact metadata for a sandbox file or directory."""
        script = r"""
import json
import os
import stat
import sys
from datetime import datetime, timezone

payload = json.loads(os.environ["MATTIN_STAT_PAYLOAD"])
path = payload["path"]

try:
    st = os.lstat(path)
except FileNotFoundError:
    print(f"[Error] Path not found: {path}")
    sys.exit(0)

mode = st.st_mode
if stat.S_ISDIR(mode):
    kind = "directory"
elif stat.S_ISLNK(mode):
    kind = "symlink"
elif stat.S_ISREG(mode):
    kind = "file"
else:
    kind = "other"

print(f"path\t{os.path.abspath(path)}")
print(f"type\t{kind}")
print(f"size\t{st.st_size}")
print(f"mode\t{oct(stat.S_IMODE(mode))[2:]}")
print(f"mtime\t{datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat().replace('+00:00', 'Z')}")

if stat.S_ISLNK(mode):
    try:
        print(f"target\t{os.readlink(path)}")
    except OSError:
        pass
elif stat.S_ISDIR(mode):
    try:
        total = len(os.listdir(path))
        visible = len([name for name in os.listdir(path) if not name.startswith(".")])
        print(f"entries\t{visible}/{total}")
    except OSError:
        pass
"""
        payload = {"path": path}
        command = (
            f"export MATTIN_STAT_PAYLOAD={shlex.quote(json.dumps(payload))}; "
            + _python_payload(script)
        )
        return _run_bash_with_recovery(
            provider,
            handle_ref,
            command,
            session_key=session_key,
            session_service=session_service,
            timeout=10,
            max_output_chars=4000,
        )

    return StructuredTool.from_function(
        func=Stat,
        name="Stat",
        description=Stat.__doc__ or "",
        args_schema=StatArgs,
    )


def _bash_tool(
    provider: SandboxProvider,
    handle_ref: _SandboxHandleRef,
    *,
    session_key: str | None = None,
    session_service: Any | None = None,
):
    def Bash(
        command: str,
        description: str | None = None,
        timeout: int | None = None,
        run_in_background: bool = False,
    ) -> str:
        """Sandbox-only operation: execute a bash command inside the sandbox."""
        timeout_s = _timeout_ms_to_seconds(timeout)
        if not run_in_background:
            return _run_bash_with_recovery(
                provider,
                handle_ref,
                command,
                session_key=session_key,
                session_service=session_service,
                timeout=timeout_s,
                max_output_chars=_BASH_OUTPUT_LIMIT,
            )

        bash_id = f"bash-{uuid.uuid4().hex[:12]}"
        base_dir = f".mattin/background/{bash_id}"
        out_file = f"{base_dir}/output.log"
        pid_file = f"{base_dir}/pid"
        status_file = f"{base_dir}/status"
        status_command = command + '; printf %s "$?" > ' + shlex.quote(status_file)
        quoted_status_command = shlex.quote(status_command)
        quoted_base_dir = shlex.quote(base_dir)
        quoted_out_file = shlex.quote(out_file)
        quoted_pid_file = shlex.quote(pid_file)
        quoted_bash_id = shlex.quote(bash_id)
        wrapped = (
            f"mkdir -p {quoted_base_dir}; "
            f"nohup bash -lc {quoted_status_command} "
            f"> {quoted_out_file} 2>&1 < /dev/null & "
            f"printf '%s' \"$!\" > {quoted_pid_file}; "
            f"printf 'Started background shell %s (pid %s)\\n' {quoted_bash_id} \"$(cat {quoted_pid_file})\""
        )
        result = _run_bash_with_recovery(
            provider,
            handle_ref,
            wrapped,
            session_key=session_key,
            session_service=session_service,
            timeout=5,
            max_output_chars=2000,
        )
        handle_ref.handle.metadata.setdefault(_BG_SHELLS_KEY, {})[bash_id] = {
            "command": command,
            "output_file": out_file,
            "pid_file": pid_file,
            "status_file": status_file,
            "offset": 0,
        }
        return result

    return StructuredTool.from_function(
        func=Bash,
        name="Bash",
        description=Bash.__doc__ or "",
        args_schema=BashArgs,
    )


def _timeout_ms_to_seconds(timeout_ms: int | None) -> int:
    if timeout_ms is None:
        return _BASH_DEFAULT_TIMEOUT_S
    return max(1, min(_BASH_MAX_TIMEOUT_S, int(timeout_ms) // 1000 or 1))


def _bash_output_tool(
    provider: SandboxProvider,
    handle_ref: _SandboxHandleRef,
    *,
    session_key: str | None = None,
    session_service: Any | None = None,
):
    def BashOutput(bash_id: str, filter: str | None = None) -> str:
        """Sandbox-only operation: retrieve new output from a background bash shell running in the sandbox."""
        shells = handle_ref.handle.metadata.get(_BG_SHELLS_KEY, {})
        info = shells.get(bash_id) if isinstance(shells, dict) else None
        if not info:
            return f"[Error] Unknown background shell: {bash_id}"
        if filter:
            try:
                re.compile(filter)
            except re.error as exc:
                return f"[Error] Invalid filter regex: {exc}"

        offset = int(info.get("offset", 0))
        out_file = str(info["output_file"])
        pid_file = str(info["pid_file"])
        status_file = str(info["status_file"])
        filter_cmd = f" | grep -E {shlex.quote(filter)}" if filter else ""
        command = (
            f"out={shlex.quote(out_file)}; pidf={shlex.quote(pid_file)}; statusf={shlex.quote(status_file)}; "
            "size=0; [ -f \"$out\" ] && size=$(wc -c < \"$out\"); "
            f"if [ \"$size\" -gt {offset} ]; then tail -c +{offset + 1} \"$out\"{filter_cmd}; fi; "
            "pid=''; [ -f \"$pidf\" ] && pid=$(cat \"$pidf\"); "
            "state=completed; exit_code=''; "
            "if [ -n \"$pid\" ] && kill -0 \"$pid\" 2>/dev/null; then state=running; "
            "elif [ -f \"$statusf\" ]; then exit_code=$(cat \"$statusf\"); fi; "
            "printf '\\n[MATTIN_BASH_STATUS size=%s state=%s exit=%s]\\n' \"$size\" \"$state\" \"$exit_code\""
        )
        result = _run_bash_with_recovery(
            provider,
            handle_ref,
            command,
            session_key=session_key,
            session_service=session_service,
            timeout=5,
            max_output_chars=_BASH_OUTPUT_LIMIT,
        )
        marker = "\n[MATTIN_BASH_STATUS "
        if marker in result:
            body, status = result.rsplit(marker, 1)
            match = re.search(r"size=(\d+)", status)
            if match:
                info["offset"] = int(match.group(1))
            return body.rstrip() + "\n" + "[Bash shell " + status.strip().rstrip("]") + "]"
        return result

    return StructuredTool.from_function(
        func=BashOutput,
        name="BashOutput",
        description=BashOutput.__doc__ or "",
        args_schema=BashOutputArgs,
    )


def _kill_shell_tool(
    provider: SandboxProvider,
    handle_ref: _SandboxHandleRef,
    *,
    session_key: str | None = None,
    session_service: Any | None = None,
):
    def KillShell(shell_id: str) -> str:
        """Sandbox-only operation: kill a running background bash shell in the sandbox."""
        shells = handle_ref.handle.metadata.get(_BG_SHELLS_KEY, {})
        info = shells.get(shell_id) if isinstance(shells, dict) else None
        if not info:
            return f"[Error] Unknown background shell: {shell_id}"
        pid_file = str(info["pid_file"])
        command = (
            f"pidf={shlex.quote(pid_file)}; "
            "if [ ! -f \"$pidf\" ]; then echo '[Error] Missing pid file'; exit 0; fi; "
            "pid=$(cat \"$pidf\"); "
            "if kill -0 \"$pid\" 2>/dev/null; then kill \"$pid\" 2>/dev/null || true; "
            "pkill -TERM -P \"$pid\" 2>/dev/null || true; "
            "echo \"Killed background shell $pid\"; else echo 'Shell is not running'; fi"
        )
        return _run_bash_with_recovery(
            provider,
            handle_ref,
            command,
            session_key=session_key,
            session_service=session_service,
            timeout=5,
            max_output_chars=2000,
        )

    return StructuredTool.from_function(
        func=KillShell,
        name="KillShell",
        description=KillShell.__doc__ or "",
        args_schema=KillShellArgs,
    )


def create_sandbox_builtin_tools(
    handle: SandboxHandle,
    provider: SandboxProvider,
    *,
    session_key: str | None = None,
    session_service: Any | None = None,
) -> list:
    """Return Claude-style builtin tools for a Linux sandbox.

    Args:
        handle:          Active sandbox handle.
        provider:        Resolved ``SandboxProvider`` instance.
        session_key:     Optional session key; used to evict the stale cache entry
                         and obtain a fresh handle on
                         :class:`~tools.sandbox.provider.SandboxExpiredError`.
        session_service: Optional :class:`~services.sandbox_session_service.SandboxSessionService`
                         instance used to recover from an expired sandbox mid-turn.

    All tools returned here share a single mutable handle reference so that a
    sandbox recovered after expiry (by any one tool call) is immediately visible
    to every other tool for the remainder of the turn.
    """
    if not _supports_bash(provider):
        return []
    read_files: set[str] = set()
    handle_ref = _SandboxHandleRef(handle)
    kwargs: dict[str, Any] = {
        "session_key": session_key,
        "session_service": session_service,
    }
    return [
        _sandbox_info_tool(provider, handle_ref, **kwargs),
        _pwd_tool(provider, handle_ref, **kwargs),
        _read_tool(provider, handle_ref, read_files, **kwargs),
        _write_tool(provider, handle_ref, read_files, **kwargs),
        _edit_tool(provider, handle_ref, read_files, **kwargs),
        _ls_tool(provider, handle_ref, **kwargs),
        _glob_tool(provider, handle_ref, **kwargs),
        _grep_tool(provider, handle_ref, **kwargs),
        _stat_tool(provider, handle_ref, **kwargs),
        _bash_tool(provider, handle_ref, **kwargs),
        _bash_output_tool(provider, handle_ref, **kwargs),
        _kill_shell_tool(provider, handle_ref, **kwargs),
    ]
