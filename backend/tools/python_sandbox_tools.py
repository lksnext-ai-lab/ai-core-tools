import os
import subprocess
import sys
import tempfile
import logging
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

MAX_OUTPUT_CHARS = 20_000
DEFAULT_TIMEOUT = 30  # seconds


def create_python_repl_tool(working_dir: str):
    """
    Create a python_repl LangChain tool bound to a specific working directory.

    The tool executes Python code in a subprocess isolated from the backend process.
    Code runs with the given working_dir as cwd, so agents can reference uploaded
    files by filename only (e.g. open('report.xlsx')) without needing full paths.

    Output files saved to working_dir are automatically accessible for download.
    """

    @tool
    def python_repl(code: str) -> str:
        """Execute Python code and return stdout + stderr.

        Use this tool to read, analyse, transform, and create files.
        Available libraries: pandas, openpyxl, numpy, os, json, csv, re, datetime.

        Files uploaded by the user are in the current working directory — reference
        them by filename only (e.g. 'report.xlsx', not a full path).

        Save output files to the current working directory and print the filename
        so the user knows what to download.

        Example:
            import pandas as pd
            df = pd.read_excel('data.xlsx')
            print(df.shape)
        """
        script_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".py",
                dir=working_dir,
                delete=False,
                encoding="utf-8",
            ) as f:
                f.write(code)
                script_path = f.name

            logger.info("python_repl using interpreter: %s", sys.executable)

            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=DEFAULT_TIMEOUT,
                cwd=working_dir,
                env=os.environ.copy(),
            )

            output = result.stdout or ""
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}\n[sandbox] interpreter: {sys.executable}"

            logger.info(
                "python_repl executed successfully in %s (exit=%d, output_len=%d)",
                working_dir,
                result.returncode,
                len(output),
            )

        except subprocess.TimeoutExpired:
            output = f"[Error] Execution timed out after {DEFAULT_TIMEOUT} seconds."
            logger.warning("python_repl timed out in %s", working_dir)
        except Exception as exc:
            output = f"[Error] Failed to execute code: {exc}"
            logger.error("python_repl unexpected error: %s", exc, exc_info=True)
        finally:
            if script_path and os.path.exists(script_path):
                try:
                    os.unlink(script_path)
                except OSError:
                    pass

        return output[:MAX_OUTPUT_CHARS]

    return python_repl
