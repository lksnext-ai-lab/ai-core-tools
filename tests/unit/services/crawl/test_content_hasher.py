"""Unit tests for content hash utilities."""
import pytest
from services.crawl.content_hasher import compute_hash, normalize_text_for_hash


def test_stable_hash():
    text = "Hello, world! This is some content."
    assert compute_hash(text) == compute_hash(text)


def test_whitespace_normalized():
    text1 = "Hello    world"
    text2 = "Hello world"
    normalized1 = normalize_text_for_hash(text1)
    normalized2 = normalize_text_for_hash(text2)
    assert compute_hash(normalized1) == compute_hash(normalized2)


def test_different_content_different_hash():
    assert compute_hash("content A") != compute_hash("content B")


def test_hash_length():
    # SHA-256 hex digest is 64 characters
    assert len(compute_hash("test")) == 64


def test_hash_is_hex():
    h = compute_hash("test")
    int(h, 16)  # raises ValueError if not hex


def test_normalize_strips_leading_trailing_whitespace():
    assert normalize_text_for_hash("  hello  ") == "hello"


def test_normalize_collapses_internal_whitespace():
    assert normalize_text_for_hash("hello   world") == "hello world"
