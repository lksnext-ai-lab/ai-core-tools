"""Blocking file I/O for async code, run in a worker thread so it never stalls the event loop."""

import asyncio
import json
import tempfile
from typing import Any


def _write_bytes(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _write_text(path: str, text: str, encoding: str) -> None:
    with open(path, "w", encoding=encoding) as f:
        f.write(text)


def _read_text(path: str, encoding: str) -> str:
    with open(path, "r", encoding=encoding) as f:
        return f.read()


def _write_json(path: str, data: Any) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _read_json(path: str) -> Any:
    with open(path, "r") as f:
        return json.load(f)


def _write_temp_file(data: bytes, suffix: str, dir: str | None) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=dir) as f:
        f.write(data)
        return f.name


async def write_bytes(path: str, data: bytes) -> None:
    await asyncio.to_thread(_write_bytes, path, data)


async def read_bytes(path: str) -> bytes:
    return await asyncio.to_thread(_read_bytes, path)


async def write_text(path: str, text: str, encoding: str = "utf-8") -> None:
    await asyncio.to_thread(_write_text, path, text, encoding)


async def read_text(path: str, encoding: str = "utf-8") -> str:
    return await asyncio.to_thread(_read_text, path, encoding)


async def write_json(path: str, data: Any) -> None:
    """Write ``data`` as indented JSON (same format as ``json.dump(data, f, indent=2)``)."""
    await asyncio.to_thread(_write_json, path, data)


async def read_json(path: str) -> Any:
    return await asyncio.to_thread(_read_json, path)


async def write_temp_file(data: bytes, suffix: str = "", dir: str | None = None) -> str:
    """Write ``data`` to a new persistent temp file (``delete=False``) and return its path."""
    return await asyncio.to_thread(_write_temp_file, data, suffix, dir)
