import os
import urllib.request
import urllib.error
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def create_download_url_tool(working_dir: str):
    """
    Create a download_url_to_workspace LangChain tool bound to a specific working directory.

    The tool fetches any URL and saves it to the conversation working directory so the
    file appears in the user's files panel and can be downloaded.  Useful for persisting
    images, PDFs, or any other artefact returned as a URL by another tool or the LLM.
    """

    @tool
    def download_url_to_workspace(url: str, filename: str) -> str:
        """Download a file from a URL and save it to the working directory.

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
            os.makedirs(working_dir, exist_ok=True)
            dest = os.path.join(working_dir, filename)
            urllib.request.urlretrieve(url, dest)
            size = os.path.getsize(dest)
            logger.info("download_url_to_workspace: saved %s (%d bytes) from %s", filename, size, url)
            return f"Saved: {filename} ({size} bytes)"
        except urllib.error.URLError as exc:
            logger.warning("download_url_to_workspace: URL error for %s: %s", url, exc)
            return f"[Error] Could not download URL: {exc}"
        except Exception as exc:
            logger.error("download_url_to_workspace: unexpected error: %s", exc)
            return f"[Error] {exc}"

    return download_url_to_workspace
