from langchain_core.tools import tool
import base64

from utils.config import get_app_config
from utils.path_safety import UnsafePathError, resolve_within


@tool
def fetch_file_in_base64(file_path: str):
    """This tool is useful to get the file in base64 format."""
    # The path comes from the LLM, so it is untrusted: only files under
    # TMP_BASE_FOLDER (where attachments live) may be read.
    try:
        safe_path = resolve_within(get_app_config()['TMP_BASE_FOLDER'], file_path)
    except UnsafePathError:
        return "Error: access to this file path is not allowed."
    with open(safe_path, "rb") as file:
        return base64.b64encode(file.read()).decode("utf-8")
