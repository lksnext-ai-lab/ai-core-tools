"""Unit tests for range parsing and bucket alignment in services.metrics_query_service."""
from datetime import datetime, timedelta

import pytest

from services.metrics_query_service import _align, parse_range

NOW = datetime(2026, 9, 26, 14, 37, 12)


@pytest.mark.parametrize("range_str, window, bucket", [
    ("24h", timedelta(hours=24), "1h"),
    ("7d", timedelta(days=7), "6h"),
    ("30d", timedelta(days=30), "1d"),
    ("90d", timedelta(days=90), "1d"),
])
def test_parse_range(range_str, window, bucket):
    since, until, bucket_label, _ = parse_range(range_str, now=NOW)
    assert until == NOW
    assert since == NOW - window
    assert bucket_label == bucket


def test_invalid_range():
    with pytest.raises(ValueError, match="Invalid range"):
        parse_range("invalid")


@pytest.mark.parametrize("length, expected", [
    (timedelta(hours=1), datetime(2026, 9, 26, 14, 0)),
    (timedelta(hours=6), datetime(2026, 9, 26, 12, 0)),  # 6h buckets start at 00/06/12/18 UTC
    (timedelta(days=1), datetime(2026, 9, 26, 0, 0)),
])
def test_align_matches_sql_bucket_starts(length, expected):
    assert _align(NOW, length) == expected
