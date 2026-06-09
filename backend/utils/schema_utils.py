import re

def sanitize_identifier(name: str) -> str:
    """
    OpenAI function/tool/schema names must match:
    ^[a-zA-Z0-9_-]+$
    """

    name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)

    if not name:
        name = "id"

    if not re.match(r"^[a-zA-Z_]", name):
        name = f"id_{name}"

    return name