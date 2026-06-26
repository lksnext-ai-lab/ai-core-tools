"""Helpers for AWS Bedrock credential handling.

Bedrock needs three pieces of information that don't map onto the single
``api_key`` column shared by every other provider:

* ``aws_access_key_id`` and ``aws_region`` \u2014 stored as JSON in the
  service's ``extra_config`` column (non-secret identifiers).
* ``aws_secret_access_key`` \u2014 stored in the standard ``api_key`` column so
  it reuses the existing masking / placeholder machinery.

This module is intentionally dependency-free (no SQLAlchemy, no LangChain)
so both the runtime builders (``aiServiceTools`` / ``embeddingTools``) and
the listing adapter can import it without circular-import risk.
"""

from __future__ import annotations

import json
from typing import Any, Optional

# Default region used when a service has no region configured. Bedrock is
# most widely available in us-east-1.
DEFAULT_BEDROCK_REGION = "us-east-1"


def parse_extra_config(raw: Any) -> dict:
    """Parse a service ``extra_config`` value into a dict.

    Accepts a JSON string, an already-parsed dict, or ``None``. Anything
    malformed degrades to an empty dict rather than raising \u2014 a bad
    config should surface as a clear "missing credentials" error later,
    not a JSON traceback.
    """
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def build_extra_config(aws_access_key_id: Optional[str], aws_region: Optional[str]) -> Optional[str]:
    """Serialise the non-secret Bedrock fields into an ``extra_config`` JSON string.

    Returns ``None`` when both fields are empty so the column stays NULL
    for non-Bedrock services.
    """
    data = {}
    if aws_access_key_id:
        data["aws_access_key_id"] = aws_access_key_id.strip()
    if aws_region:
        data["aws_region"] = aws_region.strip()
    return json.dumps(data) if data else None


def resolve_bedrock_credentials(service) -> dict:
    """Build the boto3/LangChain kwargs for a Bedrock-backed service.

    ``service`` may be an ORM model or any object exposing ``api_key`` and
    ``extra_config`` attributes (e.g. the MockAIService used by the
    connection tester).
    """
    cfg = parse_extra_config(getattr(service, "extra_config", None))
    region = (cfg.get("aws_region") or "").strip() or DEFAULT_BEDROCK_REGION
    access_key_id = (cfg.get("aws_access_key_id") or "").strip()
    secret_access_key = (getattr(service, "api_key", None) or "").strip()

    creds = {"region_name": region}
    if access_key_id:
        creds["aws_access_key_id"] = access_key_id
    if secret_access_key:
        creds["aws_secret_access_key"] = secret_access_key
    return creds
