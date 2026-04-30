from utils.error_handlers import ValidationError

def assert_vector_db_type_immutable(
    existing_value: str | None,
    requested_value: str | None,
    entity_name: str = "resource",
) -> None:
    """Raise ValidationError if the caller tries to change vector_db_type on an existing resource.

    Rules:
    - If existing_value is None  → no value locked yet; pass through.
    - If requested_value is None → caller is not touching the field; pass through.
    - If both set and EQUAL      → idempotent; pass through.
    - If both set and DIFFER     → raises ValidationError.

    Both values are compared case-insensitively after uppercasing.
    """
    if existing_value is None or requested_value is None:
        return

    if requested_value.upper() != existing_value.upper():
       
        raise ValidationError(
            f"vector_db_type cannot be changed after a {entity_name} has been created. "
            f"Delete and recreate the {entity_name} to use a different vector database."
        )


def assert_embedding_service_immutable(
    existing_id: int | None,
    requested_id: int | None,
    entity_name: str = "resource",
) -> None:
    """Raise ValidationError if the caller tries to change embedding_service_id on an existing resource.

    Rules:
    - If existing_id is None  → no service locked yet; pass through.
    - If requested_id is None → caller is not touching the field; pass through.
    - If both set and EQUAL   → idempotent; pass through.
    - If both set and DIFFER  → raises ValidationError.
    """
    if existing_id is None or requested_id is None:
        return

    if int(requested_id) != int(existing_id):
        raise ValidationError(
            f"embedding_service_id cannot be changed after a {entity_name} has been created. "
            f"The embedding model determines the vector dimensions of all indexed data. "
            f"Delete and recreate the {entity_name} to use a different embedding service."
        )
