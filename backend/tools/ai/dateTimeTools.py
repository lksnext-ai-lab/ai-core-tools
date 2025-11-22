from langchain_core.tools import tool
from datetime import datetime


@tool
def get_current_date():
    """This tool is useful to get the current date."""
    return datetime.now().strftime("%Y-%m-%d")
