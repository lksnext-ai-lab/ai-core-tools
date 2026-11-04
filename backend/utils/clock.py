"""Clock helpers.

Mattin stores timestamps as naive UTC (`DateTime` columns without a timezone),
so `datetime.utcnow()` -- deprecated since Python 3.12 -- is replaced by an
explicit aware-then-naive conversion with the same value.
"""

from datetime import datetime, timezone


def utcnow_naive() -> datetime:
    """Current UTC time as a naive datetime, matching the `DateTime` columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
