"""Unit tests for SiloSearchSchema and SiloCountRequestSchema validation."""
import pytest
from pydantic import ValidationError

from schemas.silo_schemas import SiloSearchSchema, SiloCountRequestSchema


# ---------------------------------------------------------------------------
# search_type validation
# ---------------------------------------------------------------------------

def test_valid_search_type_similarity():
    s = SiloSearchSchema(query="test", search_type="similarity")
    assert s.search_type == "similarity"


def test_valid_search_type_mmr():
    s = SiloSearchSchema(query="test", search_type="mmr", fetch_k=20, lambda_mult=0.5)
    assert s.search_type == "mmr"


def test_valid_search_type_score_threshold():
    s = SiloSearchSchema(
        query="test",
        search_type="similarity_score_threshold",
        score_threshold=0.8,
    )
    assert s.score_threshold == 0.8


def test_invalid_search_type_raises():
    with pytest.raises(ValidationError):
        SiloSearchSchema(query="test", search_type="bm25")


# ---------------------------------------------------------------------------
# score_threshold consistency
# ---------------------------------------------------------------------------

def test_score_threshold_without_correct_search_type_raises():
    with pytest.raises(ValidationError):
        SiloSearchSchema(query="test", search_type="similarity", score_threshold=0.5)


# ---------------------------------------------------------------------------
# MMR param consistency
# ---------------------------------------------------------------------------

def test_fetch_k_without_mmr_raises():
    with pytest.raises(ValidationError):
        SiloSearchSchema(query="test", search_type="similarity", fetch_k=10)


def test_lambda_mult_without_mmr_raises():
    with pytest.raises(ValidationError):
        SiloSearchSchema(query="test", search_type="similarity", lambda_mult=0.5)


# ---------------------------------------------------------------------------
# content-length validation
# ---------------------------------------------------------------------------

def test_negative_min_content_length_raises():
    with pytest.raises(ValidationError):
        SiloSearchSchema(query="test", min_content_length=-1)


def test_negative_max_content_length_raises():
    with pytest.raises(ValidationError):
        SiloSearchSchema(query="test", max_content_length=-5)


def test_min_greater_than_max_raises():
    with pytest.raises(ValidationError):
        SiloSearchSchema(query="test", min_content_length=500, max_content_length=100)


def test_valid_content_length_range():
    s = SiloSearchSchema(query="test", min_content_length=10, max_content_length=500)
    assert s.min_content_length == 10
    assert s.max_content_length == 500


def test_zero_min_content_length_is_valid():
    s = SiloSearchSchema(query="test", min_content_length=0)
    assert s.min_content_length == 0


# ---------------------------------------------------------------------------
# SiloCountRequestSchema
# ---------------------------------------------------------------------------

def test_count_schema_defaults_are_none():
    s = SiloCountRequestSchema()
    assert s.filter_metadata is None
    assert s.min_content_length is None
    assert s.max_content_length is None


def test_count_schema_accepts_filter_and_length():
    s = SiloCountRequestSchema(
        filter_metadata={"type": "pdf"},
        min_content_length=50,
        max_content_length=1000,
    )
    assert s.filter_metadata == {"type": "pdf"}
    assert s.min_content_length == 50
    assert s.max_content_length == 1000
