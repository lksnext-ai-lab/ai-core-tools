"""Single import point for the entry points exercised by the golden tests.

The refactor moves ``backend/output`` to ``backend/connectors`` and
``backend/services/output_channels``. Only this module may change when that
happens; the rest of the golden suite must stay untouched.

Patch targets used by ``conftest.py`` (all refactor-stable, none of them lives
in an ``output.*`` / ``connectors.*`` module):

* ``httpx.AsyncClient``  - providers do ``import httpx`` and call
  ``httpx.AsyncClient(...)`` at send time, so the global patch is effective.
* ``socket.getaddrinfo`` - used by ``utils.ssrf_guard.resolve_host`` at call time.
* ``uuid.uuid4``         - ``spool.py`` does ``import uuid`` and calls
  ``uuid.uuid4()`` (verified). DEPENDENCY: if the refactor ever switches to
  ``from uuid import uuid4`` in any module, the patch silently stops working
  and the golden comparison (event ids, multipart boundaries) will fail loudly.
* ``time.time``          - ``webhook.py`` does ``import time`` and calls
  ``time.time()`` (verified). Same DEPENDENCY caveat as ``uuid.uuid4``.
* env ``TMP_BASE_FOLDER`` / ``FRONTEND_URL`` and ``db.database.SessionLocal``
  (``process_delivery`` imports it lazily inside the function).

Not refactor-stable by nature (documented, not patched): ``test_destination``
reads ``datetime.now(timezone.utc)``; the tests normalise that value instead.
"""

from services.output_channels.delivery_factory import create_deliveries_for_run  # noqa: F401
from services.output_channels.delivery_processor import process_delivery  # noqa: F401
from services.output_channels.destination_test import test_destination  # noqa: F401
from services.output_channels.destinations import create_destination, update_destination  # noqa: F401
from services.output_channels.dto import destination_dto  # noqa: F401

# NOTE: ``test_destination`` is NOT a test; consumers must reference it as
# ``targets.test_destination`` (never import the bare name into a test module).
