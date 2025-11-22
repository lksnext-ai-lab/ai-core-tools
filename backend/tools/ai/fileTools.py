from langchain_core.tools import tool
import base64


@tool
def fetch_file_in_base64(file_path: str):
    """This tool is useful to get the file in base64 format."""
    with open(file_path, "rb") as file:
        return base64.b64encode(file.read()).decode("utf-8")
