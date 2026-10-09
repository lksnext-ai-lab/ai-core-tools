"""System One service import: errors must say which service they are about."""
from unittest.mock import MagicMock

import pytest

from schemas.export_schemas import ExportSystemOneServiceSchema
from services.system_one_porting import import_system_one_service


def test_a_service_with_a_bad_endpoint_is_named_in_the_error():
    item = ExportSystemOneServiceSchema(name="Nimble prod", endpoint="ftp://so.test", model_name="m", max_concurrency=1)
    with pytest.raises(ValueError, match="Nimble prod"):
        import_system_one_service(MagicMock(), item, app_id=1)
