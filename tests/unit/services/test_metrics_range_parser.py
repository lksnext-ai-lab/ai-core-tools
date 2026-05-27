"""Unit tests for the _parse_range helper in mattin_metrics.service."""
import sys
import os
from datetime import datetime, timedelta

import pytest

# Add backend to path for the indirect FastAPI import in service.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'backend'))

from mattin_metrics.service import _parse_range

TOLERANCE_SECONDS = 10


class TestParseRange:
    def test_24h(self):
        before = datetime.utcnow() - timedelta(hours=24)
        since, bucket_label, _ = _parse_range("24h")
        after = datetime.utcnow() - timedelta(hours=24)
        # since should be approximately 24h ago
        assert abs((since - before).total_seconds()) < TOLERANCE_SECONDS
        assert bucket_label == "1h"

    def test_7d(self):
        before = datetime.utcnow() - timedelta(days=7)
        since, bucket_label, _ = _parse_range("7d")
        after = datetime.utcnow() - timedelta(days=7)
        assert abs((since - before).total_seconds()) < TOLERANCE_SECONDS
        assert bucket_label == "6h"

    def test_30d(self):
        before = datetime.utcnow() - timedelta(days=30)
        since, bucket_label, _ = _parse_range("30d")
        after = datetime.utcnow() - timedelta(days=30)
        assert abs((since - before).total_seconds()) < TOLERANCE_SECONDS
        assert bucket_label == "1d"

    def test_invalid_range(self):
        with pytest.raises(ValueError, match="Invalid range"):
            _parse_range("invalid")
