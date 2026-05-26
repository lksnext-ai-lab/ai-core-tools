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
from typing import Literal

import config as settings
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field

from .provider import SandboxExpiredError, SandboxHandle, SandboxProvider


_BG_SHELLS_KEY = "_mattin_builtin_background_shells"
_DEFAULT_READ_LIMIT = 2000
_MAX_READ_LINE_CHARS = 2000
_BASH_OUTPUT_LIMIT = 30_000
_BASH_DEFAULT_TIMEOUT_S = 120
_BASH_MAX_TIMEOUT_S = 600


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


class NotebookEditArgs(BaseModel):
    notebook_path: str = Field(
        description="The absolute path to the Jupyter notebook file to edit"
    )
    new_source: str = Field(description="The new source for the cell")
    cell_id: str | None = Field(
        default=None,
        description="The ID of the cell to edit, delete, or insert after",
    )
    cell_type: Literal["code", "markdown"] | None = Field(default=None)
    edit_mode: Literal["replace", "insert", "delete"] = Field(default="replace")


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


def _abs_path_error(path: str) -> str | None:
    if not path or not path.startswith("/"):
        return "[Error] Path must be absolute inside the sandbox."
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


def _path_exists(provider: SandboxProvider, handle: SandboxHandle, file_path: str) -> bool:
    result = _run_bash(
        provider,
        handle,
        f"if [ -e {_sh(file_path)} ]; then echo __mattin_exists__; fi",
        timeout=5,
        max_output_chars=1000,
    )
    return "__mattin_exists__" in result


def _read_tool(provider: SandboxProvider, handle: SandboxHandle, read_files: set[str]):
    def Read(file_path: str, offset: int | None = None, limit: int | None = None) -> str:
        """Read file contents from the sandbox filesystem with line numbers."""
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
        output = _run_bash(provider, handle, script, max_output_chars=settings.SANDBOX_MAX_OUTPUT_CHARS)
        if "[Error]" not in output:
            read_files.add(file_path)
        return output

    return StructuredTool.from_function(
        func=Read,
        name="Read",
        description=Read.__doc__ or "",
        args_schema=ReadArgs,
    )


def _write_tool(provider: SandboxProvider, handle: SandboxHandle, read_files: set[str]):
    def Write(file_path: str, content: str) -> str:
        """Create or completely overwrite a file in the sandbox filesystem."""
        if err := _abs_path_error(file_path):
            return err
        if file_path not in read_files and _path_exists(provider, handle, file_path):
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
        return _run_bash(provider, handle, script)

    return StructuredTool.from_function(
        func=Write,
        name="Write",
        description=(Write.__doc__ or "")
        + "\n\nPrefer Edit for existing files. Read existing files before overwriting when possible.",
        args_schema=WriteArgs,
    )


def _edit_tool(provider: SandboxProvider, handle: SandboxHandle, read_files: set[str]):
    def Edit(
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> str:
        """Replace exact text in a sandbox file."""
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
        return _run_bash(provider, handle, command)

    return StructuredTool.from_function(
        func=Edit,
        name="Edit",
        description=Edit.__doc__ or "",
        args_schema=EditArgs,
    )


def _glob_tool(provider: SandboxProvider, handle: SandboxHandle):
    def Glob(pattern: str, path: str | None = None) -> str:
        """Find files by glob pattern, sorted by modification time newest first."""
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
        return _run_bash(provider, handle, command)

    return StructuredTool.from_function(
        func=Glob,
        name="Glob",
        description=Glob.__doc__ or "",
        args_schema=GlobArgs,
    )


def _grep_tool(provider: SandboxProvider, handle: SandboxHandle):
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
        """Search file contents in the sandbox, preferring ripgrep when present."""
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
        return _run_bash(provider, handle, command, max_output_chars=settings.SANDBOX_MAX_OUTPUT_CHARS)

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


def _notebook_edit_tool(provider: SandboxProvider, handle: SandboxHandle):
    def NotebookEdit(
        notebook_path: str,
        new_source: str,
        cell_id: str | None = None,
        cell_type: str | None = None,
        edit_mode: str = "replace",
    ) -> str:
        """Edit, insert, or delete a Jupyter notebook cell by cell_id."""
        if err := _abs_path_error(notebook_path):
            return err
        if edit_mode not in {"replace", "insert", "delete"}:
            return "[Error] edit_mode must be replace, insert, or delete."
        if edit_mode == "insert" and cell_type not in {"code", "markdown"}:
            return "[Error] cell_type is required for insert and must be code or markdown."
        payload = {
            "notebook_path": notebook_path,
            "new_source": new_source,
            "cell_id": cell_id,
            "cell_type": cell_type,
            "edit_mode": edit_mode,
        }
        script = r"""
import json
import os
import uuid

payload = json.loads(os.environ["MATTIN_NOTEBOOK_PAYLOAD"])
path = payload["notebook_path"]
with open(path, "r", encoding="utf-8") as fh:
    nb = json.load(fh)
cells = nb.setdefault("cells", [])
cell_id = payload.get("cell_id")
mode = payload.get("edit_mode") or "replace"
idx = None
if cell_id:
    for i, cell in enumerate(cells):
        if cell.get("id") == cell_id:
            idx = i
            break
elif cells:
    idx = 0

if mode in {"replace", "delete"} and idx is None:
    print("[Error] Cell not found.")
    raise SystemExit(0)

def source_lines(text):
    return text.splitlines(keepends=True)

if mode == "delete":
    removed = cells.pop(idx)
    print(f"Deleted cell {removed.get('id', idx)} from {path}.")
elif mode == "insert":
    new_cell = {
        "cell_type": payload["cell_type"],
        "id": uuid.uuid4().hex[:8],
        "metadata": {},
        "source": source_lines(payload.get("new_source") or ""),
    }
    if payload["cell_type"] == "code":
        new_cell.update({"execution_count": None, "outputs": []})
    insert_at = 0 if idx is None else idx + 1
    cells.insert(insert_at, new_cell)
    print(f"Inserted {payload['cell_type']} cell {new_cell['id']} at index {insert_at}.")
else:
    cell = cells[idx]
    if payload.get("cell_type"):
        cell["cell_type"] = payload["cell_type"]
        if payload["cell_type"] == "code":
            cell.setdefault("outputs", [])
            cell.setdefault("execution_count", None)
        else:
            cell.pop("outputs", None)
            cell.pop("execution_count", None)
    cell["source"] = source_lines(payload.get("new_source") or "")
    print(f"Replaced cell {cell.get('id', idx)} in {path}.")

tmp = path + ".mattin-notebook-tmp"
with open(tmp, "w", encoding="utf-8") as fh:
    json.dump(nb, fh, ensure_ascii=False, indent=1)
    fh.write("\n")
os.replace(tmp, path)
"""
        command = (
            f"export MATTIN_NOTEBOOK_PAYLOAD={shlex.quote(json.dumps(payload))}; "
            + _python_payload(script)
        )
        return _run_bash(provider, handle, command)

    return StructuredTool.from_function(
        func=NotebookEdit,
        name="NotebookEdit",
        description=NotebookEdit.__doc__ or "",
        args_schema=NotebookEditArgs,
    )


def _bash_tool(provider: SandboxProvider, handle: SandboxHandle):
    def Bash(
        command: str,
        description: str | None = None,
        timeout: int | None = None,
        run_in_background: bool = False,
    ) -> str:
        """Execute a bash command in the sandbox."""
        timeout_s = _timeout_ms_to_seconds(timeout)
        if not run_in_background:
            return _run_bash(
                provider,
                handle,
                command,
                timeout=timeout_s,
                max_output_chars=_BASH_OUTPUT_LIMIT,
            )

        bash_id = f"bash-{uuid.uuid4().hex[:12]}"
        base_dir = f".mattin/background/{bash_id}"
        out_file = f"{base_dir}/output.log"
        pid_file = f"{base_dir}/pid"
        status_file = f"{base_dir}/status"
        wrapped = (
            f"mkdir -p {shlex.quote(base_dir)}; "
            f"nohup bash -lc {shlex.quote(command + '; printf %s \"$?\" > ' + shlex.quote(status_file))} "
            f"> {shlex.quote(out_file)} 2>&1 < /dev/null & "
            f"printf '%s' \"$!\" > {shlex.quote(pid_file)}; "
            f"printf 'Started background shell %s (pid %s)\\n' {shlex.quote(bash_id)} \"$(cat {shlex.quote(pid_file)})\""
        )
        result = _run_bash(provider, handle, wrapped, timeout=5, max_output_chars=2000)
        handle.metadata.setdefault(_BG_SHELLS_KEY, {})[bash_id] = {
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


def _bash_output_tool(provider: SandboxProvider, handle: SandboxHandle):
    def BashOutput(bash_id: str, filter: str | None = None) -> str:
        """Retrieve new output from a background bash shell."""
        shells = handle.metadata.get(_BG_SHELLS_KEY, {})
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
        result = _run_bash(provider, handle, command, timeout=5, max_output_chars=_BASH_OUTPUT_LIMIT)
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


def _kill_shell_tool(provider: SandboxProvider, handle: SandboxHandle):
    def KillShell(shell_id: str) -> str:
        """Kill a running background bash shell."""
        shells = handle.metadata.get(_BG_SHELLS_KEY, {})
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
        return _run_bash(provider, handle, command, timeout=5, max_output_chars=2000)

    return StructuredTool.from_function(
        func=KillShell,
        name="KillShell",
        description=KillShell.__doc__ or "",
        args_schema=KillShellArgs,
    )


def create_sandbox_builtin_tools(
    handle: SandboxHandle,
    provider: SandboxProvider,
) -> list:
    """Return Claude-style builtin tools for a Linux sandbox."""
    if not _supports_bash(provider):
        return []
    read_files: set[str] = set()
    return [
        _read_tool(provider, handle, read_files),
        _write_tool(provider, handle, read_files),
        _edit_tool(provider, handle, read_files),
        _glob_tool(provider, handle),
        _grep_tool(provider, handle),
        _notebook_edit_tool(provider, handle),
        _bash_tool(provider, handle),
        _bash_output_tool(provider, handle),
        _kill_shell_tool(provider, handle),
    ]
