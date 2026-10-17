import logging
import os
import socket  # noqa: F401 - patch seam for existing tests (AC-30): tests patch
# `tools.ai.workspaceTools.socket.getaddrinfo`, which patches the real stdlib
# `socket` module object (the same object `utils.ssrf_guard` resolves hosts
# through), so this import must stay even though it's otherwise unused here.
import urllib.error
import urllib.parse

import requests
from langchain_core.tools import tool

from utils.ssrf_guard import validate_url

logger = logging.getLogger(__name__)

# Only plain web traffic may be fetched by this tool — anything else (file://, ftp://, …)
# is a path to local-disk or protocol-level exfiltration.
# Order matters: it is used verbatim in the "Only http/https URLs are
# allowed" error message built by utils.ssrf_guard.validate_url.
_ALLOWED_SCHEMES = ("http", "https")

# Hard cap on how much a single download may write to disk. There's no app-scoped
# upload-size setting reachable here (this tool factory only receives a working_dir,
# not an App/db session, and importing backend.models.app would risk a circular
# import), so this is a conservative, hardcoded default instead.
_MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024  # 100MB
_CHUNK_SIZE = 65536

# Connect/read timeout so a slow or hanging host can't block the calling coroutine.
_REQUEST_TIMEOUT_SECONDS = 30

# Redirects are followed manually (see below) so each hop's resolved host can be
# re-validated before it's followed; this caps how many hops we'll chase.
_MAX_REDIRECTS = 5


def _validate_url_host(url: str) -> str | None:
    """Validate a candidate URL's scheme and resolved host.

    Delegates the IP-range and host-resolution checks to the shared SSRF guard
    (``utils.ssrf_guard``), which is the only such implementation in the
    codebase. Only this tool's error message format is kept here.

    Args:
        url: The URL to validate before it is fetched.

    Returns:
        An `"[Error] ..."` string if the URL must be rejected, otherwise `None`.
    """
    result = validate_url(url, allowed_schemes=_ALLOWED_SCHEMES)
    if result is None:
        return None
    if result.reason == "blocked":
        hostname = urllib.parse.urlparse(url).hostname
        return f"[Error] Refusing to download from disallowed host: {hostname}"
    return f"[Error] {result.message}"


def create_download_url_tool(working_dir: str):
    """
    Create a download_url_to_workspace LangChain tool bound to a specific working directory.

    The tool fetches any URL and saves it to the conversation output directory so the
    file appears in the user's files panel and can be downloaded.  Useful for persisting
    images, PDFs, or any other artefact returned as a URL by another tool or the LLM.
    """

    @tool
    def download_url_to_workspace(url: str, filename: str) -> str:
        """Download a file from a URL and save it to output/.

        Use this tool whenever a tool or the model returns a URL pointing to a
        generated file (image, PDF, report, …).  The saved file will appear in
        the user's files panel and be available for download.

        Args:
            url:      The URL to download (http or https).
            filename: The filename to save as, e.g. 'image.png' or 'report.pdf'.

        Returns:
            A confirmation string with the saved filename and size.
        """
        try:
            safe_filename = os.path.basename((filename or "").replace("\\", "/"))
            if not safe_filename or safe_filename.startswith("."):
                return "[Error] Invalid filename"

            validation_error = _validate_url_host(url)
            if validation_error:
                return validation_error

            output_dir = os.path.join(working_dir, "output")
            os.makedirs(output_dir, exist_ok=True)
            dest = os.path.join(output_dir, safe_filename)

            current_url = url
            response = None
            for _ in range(_MAX_REDIRECTS + 1):
                response = requests.get(
                    current_url,
                    stream=True,
                    timeout=_REQUEST_TIMEOUT_SECONDS,
                    allow_redirects=False,
                )
                if not response.is_redirect:
                    break
                location = response.headers.get("Location")
                response.close()
                if not location:
                    return "[Error] Redirect response missing Location header"
                current_url = urllib.parse.urljoin(current_url, location)
                redirect_error = _validate_url_host(current_url)
                if redirect_error:
                    return redirect_error
            else:
                return "[Error] Too many redirects"

            with response:
                response.raise_for_status()
                content_length = response.headers.get("Content-Length")
                if content_length is not None and int(content_length) > _MAX_DOWNLOAD_BYTES:
                    return "[Error] File exceeds maximum allowed download size"

                size = 0
                with open(dest, "wb") as fh:
                    for chunk in response.iter_content(chunk_size=_CHUNK_SIZE):
                        if not chunk:
                            continue
                        size += len(chunk)
                        if size > _MAX_DOWNLOAD_BYTES:
                            fh.close()
                            os.remove(dest)
                            return "[Error] File exceeds maximum allowed download size"
                        fh.write(chunk)

            logger.info("download_url_to_workspace: saved %s (%d bytes) from %s", safe_filename, size, url)
            return f"Saved: output/{safe_filename} ({size} bytes)"
        except requests.exceptions.RequestException as exc:
            logger.warning("download_url_to_workspace: request error for %s: %s", url, exc)
            return f"[Error] Could not download URL: {exc}"
        except urllib.error.URLError as exc:
            logger.warning("download_url_to_workspace: URL error for %s: %s", url, exc)
            return f"[Error] Could not download URL: {exc}"
        except Exception as exc:
            logger.error("download_url_to_workspace: unexpected error: %s", exc)
            return f"[Error] {exc}"

    return download_url_to_workspace
