"""CreateUpdateAgentSchema: the media embedding service is required only for conversational agents."""

import pytest
from pydantic import ValidationError

from schemas.agent_schemas import CreateUpdateAgentSchema


def test_conversational_agent_without_embedding_service_is_rejected():
    with pytest.raises(ValidationError, match="media_embedding_service_id is required"):
        CreateUpdateAgentSchema(name="a", has_memory=True)


def test_conversational_agent_with_embedding_service_is_valid():
    schema = CreateUpdateAgentSchema(name="a", has_memory=True, media_embedding_service_id=3)
    assert schema.media_embedding_service_id == 3


def test_non_conversational_agent_without_embedding_service_is_valid():
    assert CreateUpdateAgentSchema(name="a", has_memory=False).media_embedding_service_id is None


def test_ocr_agent_is_not_subject_to_the_rule():
    assert CreateUpdateAgentSchema(name="a", type="ocr_agent", has_memory=True).media_embedding_service_id is None
