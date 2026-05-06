"""
Sandbox tool factory.

``create_sandbox_repl_tool`` produces the ``python_repl`` LangChain tool
backed by whatever ``SandboxProvider`` is passed in.  The tool docstring
is kept identical to the original in ``python_sandbox_tools.py`` so the
LLM receives the same guidance as before.
"""

from __future__ import annotations

from langchain_core.tools import tool

from .provider import SandboxProvider, SandboxHandle


def create_sandbox_repl_tool(handle: SandboxHandle, provider: SandboxProvider):
    """Return a ``python_repl`` LangChain tool bound to *handle* and *provider*.

    The returned tool is a drop-in replacement for the tool previously
    created by ``python_sandbox_tools.create_python_repl_tool``.
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
        return provider.run_code(handle, code)

    return python_repl
