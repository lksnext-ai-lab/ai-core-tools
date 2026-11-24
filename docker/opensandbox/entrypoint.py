#!/usr/local/bin/python
"""Entrypoint of the Mattin OpenSandbox server image.

Renders the (read-only) sandbox.toml template into /run/opensandbox/sandbox.toml
and then replaces itself with ``opensandbox-server``.  It exists to enforce two
security properties that the upstream server does not enforce on its own
(opensandbox-server 0.1.11 silently runs WITHOUT authentication when
``server.api_key`` is empty):

1. The control-plane API key comes from OPENSANDBOX_API_KEY.  If it is missing,
   too short or a known placeholder the process exits with an error instead of
   starting an unauthenticated server.  The only escape hatch is the explicit,
   off-by-default dev override OPENSANDBOX_INSECURE_SERVER=YES.
2. The API listens ONLY on this container's address on the control network
   (the one the backend uses), never on its address on the sandbox-workloads
   network.  Sandbox containers run untrusted code on that network; the server
   must reach them (server proxy) but they must not be able to reach the API.

Usage:  entrypoint.py [--config TEMPLATE] [--check]
  --check   validate the environment and exit 0/1 (used by the compose
            preflight service); does not need the Docker socket.
"""
from __future__ import annotations

import ipaddress
import os
import re
import socket
import sys

DEFAULT_TEMPLATE = os.environ.get("SANDBOX_CONFIG_PATH", "/etc/opensandbox/sandbox.toml")
RENDERED_DIR = "/run/opensandbox"
RENDERED_PATH = f"{RENDERED_DIR}/sandbox.toml"
BIND_HOST_FILE = f"{RENDERED_DIR}/bind_host"

MIN_KEY_LENGTH = 32
KEY_RE = re.compile(r"^[A-Za-z0-9._~+/=-]+$")
PLACEHOLDER_KEYS = {
    "your-secret-api-key",
    "changeme",
    "change-me",
    "secret",
    "opensandbox",
    "password",
}


def fail(msg: str) -> "None":
    sys.stderr.write(f"[opensandbox-entrypoint] FATAL: {msg}\n")
    sys.exit(1)


def resolve_api_key() -> str:
    key = (os.environ.get("OPENSANDBOX_API_KEY") or "").strip()
    insecure = (os.environ.get("OPENSANDBOX_INSECURE_SERVER") or "").strip() == "YES"
    allow_dev = (os.environ.get("OPENSANDBOX_ALLOW_INSECURE_DEV") or "").strip() == "1"
    if not key:
        if insecure and allow_dev:
            sys.stderr.write(
                "[opensandbox-entrypoint] ERROR: RUNNING INSECURE. OPENSANDBOX_INSECURE_SERVER=YES and "
                "OPENSANDBOX_ALLOW_INSECURE_DEV=1 with no OPENSANDBOX_API_KEY: the control plane runs "
                "WITHOUT authentication. Development only; never where untrusted code can run.\n"
            )
            return ""
        if insecure:
            fail(
                "OPENSANDBOX_INSECURE_SERVER=YES is set (probably left over from an old .env) but there is "
                "no OPENSANDBOX_API_KEY. Running without authentication now also requires "
                "OPENSANDBOX_ALLOW_INSECURE_DEV=1. Preferred fix: set OPENSANDBOX_API_KEY and remove "
                "OPENSANDBOX_INSECURE_SERVER."
            )
        fail(
            "OPENSANDBOX_API_KEY is empty. The OpenSandbox control plane must require an API key. "
            "Set OPENSANDBOX_API_KEY in docker/.env (generate one with: "
            "python -c \"import secrets; print(secrets.token_hex(32))\") and recreate the service. "
            "(Dev-only escape hatch: OPENSANDBOX_INSECURE_SERVER=YES plus OPENSANDBOX_ALLOW_INSECURE_DEV=1.)"
        )
    if len(key) < MIN_KEY_LENGTH:
        fail(f"OPENSANDBOX_API_KEY is too short ({len(key)} chars, minimum {MIN_KEY_LENGTH}).")
    if key.lower() in PLACEHOLDER_KEYS:
        fail("OPENSANDBOX_API_KEY is a known placeholder value; generate a random key.")
    if not KEY_RE.match(key):
        fail("OPENSANDBOX_API_KEY may only contain letters, digits and . _ ~ + / = - (hex is recommended).")
    return key


def discover_bind_host(workloads_network: str) -> str:
    """Return this container's IP on the control network (any network but the workloads one)."""
    explicit = (os.environ.get("OPENSANDBOX_BIND_HOST") or "").strip()
    if explicit:
        try:
            ipaddress.ip_address(explicit)
        except ValueError:
            fail(f"OPENSANDBOX_BIND_HOST={explicit!r} is not an IP address.")
        if explicit in ("0.0.0.0", "::"):
            fail(
                "OPENSANDBOX_BIND_HOST must not be a wildcard address: the API would become "
                "reachable from the sandbox-workloads network."
            )
        return explicit
    try:
        import docker  # type: ignore

        client = docker.from_env()
        container = client.containers.get(socket.gethostname())
        networks = container.attrs["NetworkSettings"]["Networks"]
    except Exception as exc:  # noqa: BLE001
        fail(
            f"cannot discover the control-network address via the Docker API ({exc}). "
            "Set OPENSANDBOX_BIND_HOST to this container's IP on the control network."
        )
    candidates = {
        name: net.get("IPAddress")
        for name, net in networks.items()
        if name != workloads_network and net.get("IPAddress")
    }
    if len(candidates) != 1:
        fail(
            "expected exactly one control network besides "
            f"{workloads_network!r}, found {sorted(candidates) or 'none'}. "
            "Attach the service to exactly one control network or set OPENSANDBOX_BIND_HOST."
        )
    return next(iter(candidates.values()))


def main(argv: list[str]) -> None:
    template = DEFAULT_TEMPLATE
    check_only = False
    i = 0
    while i < len(argv):
        if argv[i] == "--config" and i + 1 < len(argv):
            template = argv[i + 1]
            i += 2
        elif argv[i] == "--check":
            check_only = True
            i += 1
        else:
            fail(f"unknown argument {argv[i]!r}")

    api_key = resolve_api_key()
    workloads_network = (os.environ.get("SANDBOX_NETWORK_NAME") or "docker_sandbox-workloads").strip()
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$", workloads_network):
        fail(f"SANDBOX_NETWORK_NAME={workloads_network!r} is not a valid Docker network name.")
    log_level = (os.environ.get("OPENSANDBOX_LOG_LEVEL") or "INFO").strip().upper()
    if log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        fail(f"OPENSANDBOX_LOG_LEVEL={log_level!r} is not one of DEBUG/INFO/WARNING/ERROR/CRITICAL.")
    if check_only:
        print("[opensandbox-entrypoint] preflight OK (API key present and well-formed)")
        return

    bind_host = discover_bind_host(workloads_network)

    with open(template, encoding="utf-8") as fh:
        text = fh.read()
    # Only non-comment lines are templated (comments may mention the markers).
    lines = text.split("\n")
    for marker, value in (
        ("@@API_KEY@@", api_key),
        ("@@BIND_HOST@@", bind_host),
        ("@@SANDBOX_NETWORK@@", workloads_network),
        ("@@LOG_LEVEL@@", log_level),
    ):
        hits = [n for n, ln in enumerate(lines) if not ln.lstrip().startswith("#") and marker in ln]
        if not hits:
            fail(f"template {template} lacks the {marker} marker")
        for n in hits:
            lines[n] = lines[n].replace(marker, value)
    text = "\n".join(lines)
    if any(re.search(r"@@[A-Z_]+@@", ln) for ln in lines if not ln.lstrip().startswith("#")):
        fail("template still contains unresolved @@MARKER@@ placeholders")

    try:
        import tomllib  # Python >= 3.11
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore  # Python 3.10 (this image)
        except ImportError as exc:
            fail(f"no TOML parser available (tomllib/tomli missing in the image): {exc}")
    try:  # validate the result is TOML before handing it to the server
        tomllib.loads(text)
    except Exception as exc:  # noqa: BLE001
        fail(f"rendered configuration is not valid TOML: {exc}")

    os.makedirs(RENDERED_DIR, mode=0o700, exist_ok=True)
    fd = os.open(RENDERED_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        out.write(text)
    with open(BIND_HOST_FILE, "w", encoding="utf-8") as out:
        out.write(bind_host)

    print(
        f"[opensandbox-entrypoint] API listens on {bind_host}:8080 only (workloads network "
        f"{workloads_network!r} excluded); authentication "
        f"{'ENABLED' if api_key else 'DISABLED (insecure dev override)'}",
        flush=True,
    )
    os.execvp("opensandbox-server", ["opensandbox-server", "--config", RENDERED_PATH])


if __name__ == "__main__":
    main(sys.argv[1:])
