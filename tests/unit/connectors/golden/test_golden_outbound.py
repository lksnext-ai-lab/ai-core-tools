"""Golden fixtures freezing the bytes sent and the rows persisted by the output layer.

Run with ``GOLDEN_UPDATE=1`` only to (re)generate the fixtures. Entry points come
from ``_targets`` exclusively.
"""

import hashlib
import uuid
from pathlib import Path

import pytest

from models.output_delivery import OutputDelivery

from . import _targets as targets
from .golden_support import (
    BEARER_TOKEN, HMAC_KEY, HMAC_SECRET, TEAMS_URL, WEBHOOK_URL, bind, check_golden, final_state,
    make_task_and_run, mask_now, persisted_state, verify_and_mask_signature,
)

LONG_TEXT = "Resultado detallado del informe diario. " * 40  # > 1200 chars
HMAC = {"auth_mode": "hmac_sha256"}


def _teams(db, name="Teams", content_mode="result"):
    destination = targets.create_destination(
        db, app_id=1, created_by=1, name=name, webhook_url=TEAMS_URL, content_mode=content_mode,
    )
    return destination


def _webhook(db, name, config, credentials, content_mode="result"):
    return targets.create_destination(
        db, app_id=1, created_by=1, name=name, webhook_url=WEBHOOK_URL, provider_key="webhook",
        public_config=config, credentials=credentials, content_mode=content_mode,
    )


async def _scenario(factory, recorder, name, *, output_text, output_files, destinations, artifacts=None,
                    attachment_error=None, bind_order=None, expected_requests):
    """destinations: callables (db) -> OutputDestination, created in list order.

    ``bind_order`` is a list of indices into ``destinations`` giving the order in
    which bindings are created (default: same as creation order).
    ``expected_requests`` is the number of HTTP requests the recorder must have seen,
    so a bypassed httpx patch cannot pass silently.
    """
    db = factory()
    try:
        task, run = make_task_and_run(db, output_text=output_text, output_files=output_files)
        created = [build(db) for build in destinations]
        for index in (bind_order if bind_order is not None else range(len(created))):
            bind(db, created[index])
        targets.create_deliveries_for_run(db, task=task, run=run, artifacts=artifacts, attachment_error=attachment_error)
        db.commit()
        persisted = persisted_state(db, factory.spool)
        ids = [row.id for row in db.query(OutputDelivery.id).order_by(OutputDelivery.id)]
        for delivery_id in ids:
            await targets.process_delivery(delivery_id, 0)
        assert len(recorder.requests) == expected_requests, "httpx patch bypassed or send count changed"
        requests = [verify_and_mask_signature(item, HMAC_KEY) for item in recorder.dump()]
        data = {"persisted": persisted, "requests": requests, "final": final_state(db)}
        check_golden(name, data)
        return data
    finally:
        db.close()


FILES_2 = [
    {"file_id": "f-1", "filename": "informe.pdf", "file_type": "pdf"},
    {"file_id": "f-2", "filename": "datos.csv", "file_type": "csv"},
]
TEXT_WITH_LINKS = "Resumen: ver file://f-1 y file://otro.\n" + LONG_TEXT


@pytest.mark.usefixtures("deterministic")
class TestGoldenDeliveries:
    async def test_g01_teams_no_files(self, golden_outbox, http_recorder):
        await _scenario(golden_outbox, http_recorder, "G01_teams_no_files",
                        output_text="Todo correcto.", output_files=[], destinations=[lambda db: _teams(db)], expected_requests=1)

    async def test_g02_teams_excerpt_with_files(self, golden_outbox, http_recorder):
        await _scenario(golden_outbox, http_recorder, "G02_teams_excerpt_files",
                        output_text=TEXT_WITH_LINKS, output_files=FILES_2,
                        destinations=[lambda db: _teams(db, content_mode="excerpt")], expected_requests=1)

    async def test_g03_teams_link_only(self, golden_outbox, http_recorder):
        await _scenario(golden_outbox, http_recorder, "G03_teams_link_only",
                        output_text="Texto que no debe enviarse.", output_files=FILES_2,
                        destinations=[lambda db: _teams(db, content_mode="link_only")], expected_requests=1)

    async def test_g04_webhook_hmac_json(self, golden_outbox, http_recorder):
        data = await _scenario(golden_outbox, http_recorder, "G04_webhook_hmac_json",
                        output_text="Resumen file://f-1", output_files=FILES_2,
                        destinations=[lambda db: _webhook(db, "Hook", dict(HMAC, include_attachments=False),
                                                          {"signing_secret": HMAC_SECRET})], expected_requests=1)
        # Sanity: G04 is the first webhook event, so it takes the first uuid4 of the sequence.
        assert data["persisted"][0]["payload"]["event_id"] == str(uuid.UUID(int=1))

    async def test_g05_webhook_bearer(self, golden_outbox, http_recorder):
        await _scenario(golden_outbox, http_recorder, "G05_webhook_bearer",
                        output_text="Hecho.", output_files=[],
                        destinations=[lambda db: _webhook(db, "Hook", {"auth_mode": "bearer"},
                                                          {"bearer_token": BEARER_TOKEN})], expected_requests=1)

    async def test_g06_webhook_none_dedup(self, golden_outbox, http_recorder):
        await _scenario(golden_outbox, http_recorder, "G06_webhook_none_dedup",
                        output_text="Hecho.", output_files=[],
                        destinations=[lambda db: _webhook(db, "Hook", {"auth_mode": "none", "receiver_deduplicates": True},
                                                          None)], expected_requests=1)

    async def test_g07_webhook_multipart_two_files(self, golden_outbox, http_recorder):
        artifacts = _write_artifacts(golden_outbox.spool, run_id=1, files=[
            ("f-1", "informe.txt", b"Linea 1 del informe\nLinea 2\n"),
            ("f-2", "datos.csv", b"a,b\n1,2\n3,4\n"),
        ])
        await _scenario(golden_outbox, http_recorder, "G07_webhook_multipart",
                        output_text="Ver file://f-1 y file://f-2", output_files=FILES_2,
                        destinations=[lambda db: _webhook(db, "Hook", dict(HMAC, include_attachments=True),
                                                          {"signing_secret": HMAC_SECRET})],
                        artifacts=artifacts, expected_requests=1)

    async def test_g08_webhook_attachment_error(self, golden_outbox, http_recorder):
        await _scenario(golden_outbox, http_recorder, "G08_webhook_attachment_error",
                        output_text="Hecho.", output_files=FILES_2,
                        destinations=[lambda db: _webhook(db, "Hook", {"auth_mode": "none", "include_attachments": True}, None)],
                        attachment_error="Required run output files could not be captured for this webhook.", expected_requests=0)

    async def test_g09_three_bindings_uuid_order(self, golden_outbox, http_recorder):
        """Pins the CURRENT, implicit delivery order; it is not a contract.

        ``create_deliveries_for_run`` queries bindings without ORDER BY, so the order
        (and with it the order in which ``uuid4`` is consumed) is whatever SQLite returns
        (insertion order). Creation order, binding order and name order all differ here:
        creation: C-multipart, B-hmac, A-teams; binding: B-hmac, A-teams, C-multipart;
        name order: A-teams, B-hmac, C-multipart. Adding an ORDER BY is a logged follow-up.
        """
        artifacts = _write_artifacts(golden_outbox.spool, run_id=1, files=[("f-1", "informe.txt", b"Contenido\n")])
        await _scenario(golden_outbox, http_recorder, "G09_three_bindings",
                        output_text="Ver file://f-1", output_files=FILES_2[:1],
                        destinations=[
                            lambda db: _webhook(db, "C-multipart", dict(HMAC, include_attachments=True),
                                                {"signing_secret": HMAC_SECRET}),
                            lambda db: _webhook(db, "B-hmac", dict(HMAC), {"signing_secret": HMAC_SECRET}),
                            lambda db: _teams(db, name="A-teams"),
                        ], bind_order=[1, 2, 0], artifacts=artifacts, expected_requests=3)


def _write_artifacts(spool: Path, *, run_id: int, files):
    root = spool / "artifacts" / str(run_id)
    root.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for index, (file_id, filename, data) in enumerate(files, start=1):
        key = f"artifacts/{run_id}/{hashlib.sha256(file_id.encode()).hexdigest()}.bin"
        (spool / key).write_bytes(data)
        artifacts.append({
            "file_id": file_id, "filename": filename, "content_type": "text/plain" if filename.endswith(".txt") else "text/csv",
            "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "part_name": f"file_{index}", "object_key": key,
        })
    return artifacts


@pytest.mark.usefixtures("deterministic")
class TestGoldenDestinationTest:
    async def _run(self, factory, recorder, name, destination_builder, key=None):
        db = factory()
        try:
            destination = destination_builder(db)
            receipt = await targets.test_destination(destination)
            assert len(recorder.requests) == 1, "httpx patch bypassed or send count changed"
            requests = [mask_now(verify_and_mask_signature(item, key)) for item in recorder.dump()]
            check_golden(name, {"receipt": receipt, "requests": requests})
        finally:
            db.close()

    async def test_g10_teams(self, golden_outbox, http_recorder):
        await self._run(golden_outbox, http_recorder, "G10_test_teams", lambda db: _teams(db))

    async def test_g11_webhook_hmac(self, golden_outbox, http_recorder):
        await self._run(golden_outbox, http_recorder, "G11_test_webhook_hmac",
                        lambda db: _webhook(db, "Hook", dict(HMAC), {"signing_secret": HMAC_SECRET}), HMAC_KEY)

    async def test_g12_webhook_hmac_multipart(self, golden_outbox, http_recorder):
        await self._run(golden_outbox, http_recorder, "G12_test_webhook_hmac_multipart",
                        lambda db: _webhook(db, "Hook", dict(HMAC, include_attachments=True),
                                            {"signing_secret": HMAC_SECRET}), HMAC_KEY)

    async def test_g13_webhook_bearer(self, golden_outbox, http_recorder):
        await self._run(golden_outbox, http_recorder, "G13_test_webhook_bearer",
                        lambda db: _webhook(db, "Hook", {"auth_mode": "bearer"}, {"bearer_token": BEARER_TOKEN}))

    async def test_g14_webhook_none(self, golden_outbox, http_recorder):
        await self._run(golden_outbox, http_recorder, "G14_test_webhook_none",
                        lambda db: _webhook(db, "Hook", {"auth_mode": "none"}, None))


class TestGoldenDestinationPersistence:
    """G15: only these fixtures change with CB-2 (step_011)."""

    def test_g15_create_destination_persistence(self, golden_outbox):
        db = golden_outbox()
        try:
            self._g15(db)
        finally:
            db.close()

    def _g15(self, db):
        cases = {
            "teams_credentials_none": lambda: targets.create_destination(
                db, app_id=1, created_by=1, name="t-none", webhook_url=TEAMS_URL, credentials=None),
            "teams_credentials_empty": lambda: targets.create_destination(
                db, app_id=1, created_by=1, name="t-empty", webhook_url=TEAMS_URL, credentials={}),
            "webhook_none_credentials_empty": lambda: _webhook(db, "w-none-empty", {"auth_mode": "none"}, {}),
            "webhook_none_credentials_omitted": lambda: _webhook(db, "w-none-omitted", {"auth_mode": "none"}, None),
            "webhook_hmac": lambda: _webhook(db, "w-hmac", dict(HMAC), {"signing_secret": HMAC_SECRET}),
        }
        result = {}
        for label, build in cases.items():
            destination = build()
            db.expire_all()
            dto = targets.destination_dto(destination)
            dto.pop("created_at"), dto.pop("updated_at"), dto.pop("id")
            result[label] = {
                "public_config": destination.public_config,
                "credentials": destination.credentials,
                "credentials_is_none": destination.credentials is None,
                "dto": dto,
            }
        check_golden("G15_destination_persistence", result)
