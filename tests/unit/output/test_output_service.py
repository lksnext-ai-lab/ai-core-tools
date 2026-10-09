"""Destination management, outbox creation and dispatch in ``output.service``."""

import asyncio
import hashlib
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from models.output_delivery import OutputArtifact, OutputDelivery, OutputDeliveryAttempt, ScheduledTaskOutputBinding
from output import service
from output.teams_workflow import DeliveryError
from utils.clock import utcnow_naive

from .factories import HMAC_SECRET, TEAMS_URL, WEBHOOK_URL, make_destination, make_run, make_task

HMAC_CONFIG = {"auth_mode": "hmac_sha256"}
HMAC_CREDENTIALS = {"signing_secret": HMAC_SECRET}


def _bind(db, destination, *, task_id=1, binding_id=None):
    binding = ScheduledTaskOutputBinding(id=binding_id, scheduled_task_id=task_id, destination_id=destination.id)
    db.add(binding)
    db.flush()
    return binding


def _artifact(spool, file_id="f-1", filename="report.csv", data=b"a,b\n1,2\n"):
    key = f"artifacts/1/{file_id}.bin"
    path = spool / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"file_id": file_id, "filename": filename, "content_type": "text/csv", "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "part_name": "file_1", "object_key": key}


class FakeProvider:
    """Records ``send`` calls and returns or raises a configured outcome."""

    def __init__(self, outcome=None, on_send=None):
        self.outcome = outcome if outcome is not None else {"http_status": 202}
        self.on_send = on_send
        self.calls = []

    async def send(self, secret, payload, **options):
        self.calls.append((secret, payload, options))
        if self.on_send:
            self.on_send(secret, payload, options)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


# --------------------------------------------------------------------------- destinations


class TestCreateDestination:
    def test_creates_teams_destination(self, outbox):
        with outbox() as db:
            destination = service.create_destination(db, app_id=1, created_by=7, name="  Alerts ", webhook_url=TEAMS_URL)
            dto = service.destination_dto(destination)
        assert dto["name"] == "Alerts"
        assert dto["has_secret"] is True
        assert dto["has_credentials"] is False
        assert dto["public_config"] == {}

    def test_creates_webhook_destination_with_validated_config(self, outbox):
        with outbox() as db:
            destination = service.create_destination(
                db, app_id=1, created_by=7, name="Hook", webhook_url=WEBHOOK_URL, provider_key="webhook",
                public_config=HMAC_CONFIG, credentials=HMAC_CREDENTIALS,
            )
        assert destination.public_config == {"schema_version": "1", "auth_mode": "hmac_sha256",
                                             "receiver_deduplicates": False, "include_attachments": False}
        assert service.destination_dto(destination)["has_credentials"] is True

    @pytest.mark.parametrize("kwargs, message", [
        ({"name": "   "}, "required"),
        ({"name": "x" * 256}, "too long"),
        ({"content_mode": "everything"}, "content mode"),
        ({"provider_key": "carrier-pigeon"}, "Unsupported output provider"),
        ({"public_config": {"auth_mode": "none"}}, "do not accept"),
        ({"credentials": {"bearer_token": "t"}}, "do not accept"),
    ])
    def test_rejects_invalid_input(self, outbox, kwargs, message):
        arguments = {"app_id": 1, "created_by": 1, "name": "Alerts", "webhook_url": TEAMS_URL, **kwargs}
        with outbox() as db, pytest.raises(ValueError, match=message):
            service.create_destination(db, **arguments)

    def test_duplicate_name_in_app_is_rejected(self, outbox):
        with outbox() as db:
            service.create_destination(db, app_id=1, created_by=1, name="Alerts", webhook_url=TEAMS_URL)
            with pytest.raises(ValueError, match="already exists"):
                service.create_destination(db, app_id=1, created_by=1, name="Alerts", webhook_url=TEAMS_URL)


class TestUpdateDestination:
    def test_updates_name_enabled_and_mode(self, outbox):
        with outbox() as db:
            destination = make_destination()
            db.add(destination)
            db.commit()
            service.update_destination(db, destination, {"name": " Renamed ", "enabled": False, "content_mode": "excerpt"})
        assert (destination.name, destination.enabled, destination.content_mode) == ("Renamed", False, "excerpt")

    @pytest.mark.parametrize("changes, message", [
        ({"name": " "}, "required"),
        ({"content_mode": "everything"}, "content mode"),
    ])
    def test_rejects_invalid_changes(self, outbox, changes, message):
        with outbox() as db:
            destination = make_destination()
            db.add(destination)
            db.commit()
            with pytest.raises(ValueError, match=message):
                service.update_destination(db, destination, changes)

    def test_teams_secret_can_rotate_on_same_workflow(self, outbox):
        rotated = TEAMS_URL.replace("sig=secret", "sig=rotated")
        with outbox() as db:
            destination = make_destination()
            db.add(destination)
            db.commit()
            service.update_destination(db, destination, {"webhook_url": rotated})
        assert destination.webhook_url == rotated

    def test_teams_workflow_cannot_change(self, outbox):
        with outbox() as db:
            destination = make_destination()
            db.add(destination)
            db.commit()
            with pytest.raises(ValueError, match="Workflow or channel"):
                service.update_destination(db, destination, {"webhook_url": "https://prod.logic.azure.com/workflows/other"})

    def test_webhook_config_and_credentials_can_change(self, outbox):
        with outbox() as db:
            destination = make_destination(provider_key="webhook", config=HMAC_CONFIG, credentials=HMAC_CREDENTIALS)
            db.add(destination)
            db.commit()
            service.update_destination(db, destination, {
                "public_config": {"auth_mode": "bearer"}, "credentials": {"bearer_token": "token-1"},
                "webhook_url": WEBHOOK_URL + "?",
            })
            assert destination.public_config["auth_mode"] == "bearer"
            assert destination.credentials == {"bearer_token": "token-1"}

            service.update_destination(db, destination, {"public_config": {"auth_mode": "none"}, "clear_credentials": True})
            assert destination.credentials is None

    def test_webhook_endpoint_cannot_change(self, outbox):
        with outbox() as db:
            destination = make_destination(provider_key="webhook", config={"auth_mode": "none"})
            db.add(destination)
            db.commit()
            with pytest.raises(ValueError, match="new destination"):
                service.update_destination(db, destination, {"webhook_url": "https://hooks.example.com/other"})

    def test_duplicate_name_is_rejected(self, outbox):
        with outbox() as db:
            db.add_all([make_destination(1, name="A"), make_destination(2, name="B")])
            db.commit()
            second = service.get_destination(db, app_id=1, destination_id=2)
            with pytest.raises(ValueError, match="already exists"):
                service.update_destination(db, second, {"name": "A"})


def test_get_destination_is_scoped_to_app(outbox):
    with outbox() as db:
        db.add(make_destination())
        db.commit()
        assert service.get_destination(db, app_id=1, destination_id=1).id == 1
        with pytest.raises(ValueError, match="not found"):
            service.get_destination(db, app_id=2, destination_id=1)


# --------------------------------------------------------------------------- bindings


class TestTaskBindings:
    def test_replace_adds_disables_and_lists_bindings(self, outbox):
        with outbox() as db:
            task = make_task()
            db.add_all([task, make_destination(1, name="B"), make_destination(2, name="A", provider_key="webhook",
                                                                          config={"include_attachments": True})])
            db.commit()

            listed = service.replace_task_bindings(db, task=task, app_id=1, bindings=[
                {"destination_id": 1}, {"destination_id": 2},
            ])
            assert [item["destination_name"] for item in listed] == ["A", "B"]
            assert listed[0]["include_attachments"] is True

            listed = service.replace_task_bindings(db, task=task, app_id=1, bindings=[{"destination_id": 2}], commit=False)
            assert [item["destination_id"] for item in listed] == [2]
            assert db.query(ScheduledTaskOutputBinding).filter_by(destination_id=1).one().enabled is False

    def test_duplicate_destination_is_rejected(self, outbox):
        with outbox() as db:
            task = make_task()
            db.add_all([task, make_destination()])
            db.commit()
            with pytest.raises(ValueError, match="only be selected once"):
                service.replace_task_bindings(db, task=task, app_id=1, bindings=[{"destination_id": 1}, {"destination_id": 1}])

    def test_disabled_destination_is_not_ready(self, outbox):
        with outbox() as db:
            task = make_task()
            db.add_all([task, make_destination(enabled=False)])
            db.commit()
            with pytest.raises(ValueError, match="not ready"):
                service.replace_task_bindings(db, task=task, app_id=1, bindings=[{"destination_id": 1}])


# --------------------------------------------------------------------------- payloads


def test_teams_payload_handles_aware_times_and_skips_files_without_id():
    task = SimpleNamespace(id=4, app_id=3, name="Daily")
    run = SimpleNamespace(id=12, status="succeeded", output_text="See file://report.csv",
                          scheduled_time=datetime(2026, 10, 1, 10, 0, tzinfo=timezone(timedelta(hours=2))),
                          output_files=[{"filename": "no-id.txt"}, {"file_id": "f 1", "filename": "report.csv"}])
    binding = SimpleNamespace(destination=SimpleNamespace(content_mode="result"))
    serialized = str(service._run_payload(task, run, binding))
    assert "08:00:00+00:00" in serialized
    assert "/files/f%201" in serialized
    assert "file://" not in serialized


@pytest.mark.parametrize("mode", ["result", "excerpt", "link_only"])
def test_webhook_event_respects_content_mode(mode):
    task = SimpleNamespace(id=4, app_id=3, name="Daily")
    files = [{"file_id": f"f{index}", "filename": f"{index}.txt"} for index in range(55)] + [{"filename": "skipped"}]
    run = SimpleNamespace(id=12, scheduled_task_id=4, status="succeeded", scheduled_time=datetime(2026, 10, 1),
                          finished_at=datetime(2026, 10, 1, 0, 5), output_files=files,
                          output_text="x" * 5000 + " file://f1 file://elsewhere")
    binding = SimpleNamespace(destination=SimpleNamespace(content_mode=mode))
    event = service._run_webhook_event(task, run, binding, "evt-1", [])
    content = event["content"]
    assert event["run"]["completed_at"] == "2026-10-01T00:05:00Z"
    if mode == "link_only":
        assert content["text"] is None and content["files"] == []
        assert content["files_truncated"] is False
    else:
        assert len(content["files"]) == 50 and content["files_truncated"] is True
        assert content["text_truncated"] is (mode == "excerpt")
        assert len(content["text"]) == (4000 if mode == "excerpt" else len(content["text"]))


def test_json_body_is_bounded():
    assert service._json_body({"b": 1, "a": "ñ"}) == '{"a":"ñ","b":1}'.encode("utf-8")
    with pytest.raises(ValueError, match="256 KiB"):
        service._json_body({"text": "x" * (256 * 1024)})


# --------------------------------------------------------------------------- spool


class TestSpool:
    @pytest.mark.parametrize("key", ["/etc/passwd", "../escape", "a/../../escape"])
    def test_rejects_unsafe_references(self, outbox, key):
        with pytest.raises(ValueError, match="Invalid output spool reference"):
            service._safe_spool_file(key)

    def test_rejects_symlinked_parents(self, outbox, tmp_path):
        (outbox.spool / "link").symlink_to(tmp_path)
        with pytest.raises(ValueError, match="Invalid output spool reference"):
            service._safe_spool_file("link/file.bin")

    def test_cleanup_removes_only_old_unreferenced_files(self, outbox, tmp_path):
        old = datetime.now().timestamp() - 7200
        referenced_artifact = outbox.spool / "artifacts/1/kept.bin"
        referenced_body = outbox.spool / "deliveries/kept.multipart"
        orphan = outbox.spool / "deliveries/orphan.multipart"
        recent = outbox.spool / "deliveries/recent.multipart"
        for path in (referenced_artifact, referenced_body, orphan, recent):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"data")
        for path in (referenced_artifact, referenced_body, orphan):
            os.utime(path, (old, old))
        (outbox.spool / "artifacts/2").mkdir(parents=True)
        (outbox.spool / "outside-link").symlink_to(tmp_path)
        with outbox() as db:
            db.add(OutputArtifact(run_id=1, file_id="kept", filename="kept", content_type="text/plain",
                                  size_bytes=4, sha256="0" * 64, object_key="artifacts/1/kept.bin"))
            db.add(OutputDelivery(run_id=1, binding_id=1, request_body_path="deliveries/kept.multipart"))
            db.commit()
            assert service.cleanup_spool_files(db) == 1
            assert service.cleanup_spool_files(db, grace_seconds=0, max_files=0) == 0
        assert not orphan.exists()
        assert referenced_artifact.exists() and referenced_body.exists() and recent.exists()
        assert not (outbox.spool / "artifacts/2").exists()


class TestMultipart:
    def test_writes_payload_and_attachment_parts(self, outbox):
        artifact = _artifact(outbox.spool, filename="report.tar.gz")
        path = outbox.spool / "deliveries/request.multipart"
        content_type, size, digest = service._write_multipart(path, {"event_id": "e"}, [artifact])
        body = path.read_bytes()
        boundary = content_type.split("boundary=")[1]
        assert size == len(body) and digest == hashlib.sha256(body).hexdigest()
        assert body.startswith(f"--{boundary}\r\n".encode()) and body.endswith(f"--{boundary}--\r\n".encode())
        assert b'filename="file_1.gz"' in body and b"a,b\n1,2\n" in body

    def test_missing_attachment_leaves_no_partial_file(self, outbox, monkeypatch):
        artifact = _artifact(outbox.spool)
        (outbox.spool / artifact["object_key"]).unlink()
        # Simulate the file disappearing after the boundary scan.
        monkeypatch.setattr(service, "_file_contains", lambda path, needle: False)
        path = outbox.spool / "deliveries/request.multipart"
        with pytest.raises(ValueError, match="missing"):
            service._write_multipart(path, {"event_id": "e"}, [artifact])
        assert list(path.parent.iterdir()) == []

    def test_tampered_attachment_fails_integrity_check(self, outbox):
        artifact = {**_artifact(outbox.spool), "sha256": "0" * 64}
        with pytest.raises(ValueError, match="integrity"):
            service._write_multipart(outbox.spool / "deliveries/request.multipart", {"event_id": "e"}, [artifact])

    def test_file_contains_spans_chunk_boundaries(self, tmp_path):
        path = tmp_path / "blob"
        path.write_bytes(b"x" * (256 * 1024 - 3) + b"needle")
        assert service._file_contains(path, b"needle") is True
        assert service._file_contains(path, b"absent") is False


# --------------------------------------------------------------------------- run file capture


class TestCaptureRunFiles:
    @pytest.fixture
    def capture_env(self, outbox, tmp_path, monkeypatch):
        temp_root = tmp_path / "tmp"
        (temp_root / "uploads").mkdir(parents=True)
        refs = []

        class FakeFileService:
            async def list_attached_files(self, **kwargs):
                return refs

        def run_on_private_loop(coroutine):
            # asyncio.run() would clear the main thread's event loop for later tests.
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coroutine)
            finally:
                loop.close()

        monkeypatch.setattr(service.asyncio, "run", run_on_private_loop)
        monkeypatch.setattr("services.file_management_service.FileManagementService", FakeFileService)
        monkeypatch.setattr("services.scheduled_task_service.task_user_context", lambda task: None)
        monkeypatch.setattr("utils.config.get_app_config", lambda: {"TMP_BASE_FOLDER": str(temp_root)})
        return SimpleNamespace(root=temp_root, refs=refs)

    def _run(self, files):
        return SimpleNamespace(id=1, conversation_id=5, output_files=files)

    def test_captures_files_into_spool_and_reuses_captured_copies(self, outbox, capture_env):
        (capture_env.root / "uploads/report.csv").write_bytes(b"1,2\n")
        capture_env.refs.append({"file_id": "f-1", "file_path": "uploads/report.csv", "mime_type": "bad mime"})
        run = self._run([{"file_id": "f-1", "filename": "report.csv"}, {"filename": "no id"}])

        first = service._capture_run_files_sync(make_task(), run)
        second = service._capture_run_files_sync(make_task(), run)

        assert first == second
        assert first[0]["content_type"] == "application/octet-stream"
        assert first[0]["sha256"] == hashlib.sha256(b"1,2\n").hexdigest()
        assert (outbox.spool / first[0]["object_key"]).read_bytes() == b"1,2\n"

    @pytest.mark.parametrize("files, refs, message", [
        ([{"file_id": str(index)} for index in range(11)], [], "limit is 10"),
        ([{"file_id": "f-1"}], [], "unavailable for webhook"),
        ([{"file_id": "f-1"}], [{"file_id": "f-1", "file_path": "/etc/passwd"}], "path is unavailable"),
        ([{"file_id": "f-1"}], [{"file_id": "f-1", "file_path": "uploads/missing.csv"}], ""),
    ])
    def test_rejects_unavailable_files(self, outbox, capture_env, files, refs, message):
        capture_env.refs.extend(refs)
        with pytest.raises((ValueError, FileNotFoundError), match=message):
            service._capture_run_files_sync(make_task(), self._run(files))

    def test_rejects_symlinked_source(self, outbox, capture_env, tmp_path):
        (tmp_path / "secret").write_bytes(b"secret")
        (capture_env.root / "uploads/link.csv").symlink_to(tmp_path / "secret")
        capture_env.refs.append({"file_id": "f-1", "file_path": "uploads/link.csv"})
        with pytest.raises(ValueError, match="not safe"):
            service._capture_run_files_sync(make_task(), self._run([{"file_id": "f-1"}]))

    def test_rejects_oversized_files(self, outbox, capture_env):
        with open(capture_env.root / "uploads/big.bin", "wb") as handle:
            handle.truncate(10 * 1024 * 1024 + 1)
        capture_env.refs.append({"file_id": "f-1", "file_path": "uploads/big.bin"})
        with pytest.raises(ValueError, match="10 MiB each"):
            service._capture_run_files_sync(make_task(), self._run([{"file_id": "f-1"}]))
        assert list((outbox.spool / "artifacts/1").iterdir()) == []


class TestPrepareRunAttachments:
    @pytest.mark.asyncio
    async def test_skips_capture_without_attachment_destinations(self, outbox):
        with outbox() as db:
            task = make_task()
            db.add_all([task, make_destination(provider_key="webhook", config={"include_attachments": False})])
            _bind(db, make_destination(1))
            assert await service.prepare_run_attachments(db, task=task, run=make_run()) == ([], None)

    @pytest.mark.asyncio
    async def test_reports_capture_failures(self, outbox, monkeypatch):
        def fail(task, run):
            raise ValueError("boom")

        monkeypatch.setattr(service, "_capture_run_files_sync", fail)
        with outbox() as db:
            task = make_task()
            destination = make_destination(provider_key="webhook", config={"include_attachments": True})
            db.add_all([task, destination])
            _bind(db, destination)
            artifacts, error = await service.prepare_run_attachments(db, task=task, run=make_run())
        assert artifacts == [] and "could not be captured" in error

    @pytest.mark.asyncio
    async def test_returns_captured_artifacts(self, outbox, monkeypatch):
        monkeypatch.setattr(service, "_capture_run_files_sync", lambda task, run: [{"file_id": "f-1"}])
        with outbox() as db:
            task = make_task()
            destination = make_destination(provider_key="webhook", config={"include_attachments": True})
            db.add_all([task, destination])
            _bind(db, destination)
            assert await service.prepare_run_attachments(db, task=task, run=make_run()) == ([{"file_id": "f-1"}], None)


# --------------------------------------------------------------------------- outbox creation


class TestCreateDeliveries:
    def _setup(self, db, destination, *, text="Result"):
        task, run = make_task(), make_run(text=text)
        db.add_all([task, run, destination])
        _bind(db, destination)
        return task, run

    def test_webhook_delivery_with_attachments_spools_multipart_body(self, outbox):
        artifact = _artifact(outbox.spool)
        with outbox() as db:
            destination = make_destination(provider_key="webhook", config={"include_attachments": True, "auth_mode": "none"})
            task, run = self._setup(db, destination)
            [delivery] = service.create_deliveries_for_run(db, task=task, run=run, artifacts=[artifact])
            db.commit()
            # Idempotent: the same run/binding returns the existing outbox row.
            assert service.create_deliveries_for_run(db, task=task, run=run, artifacts=[artifact]) == [delivery]
            assert db.query(OutputArtifact).one().file_id == "f-1"
        assert delivery.status == "pending"
        assert delivery.destination_snapshot["content_type"].startswith("multipart/form-data")
        assert (outbox.spool / delivery.request_body_path).stat().st_size == delivery.request_body_size
        assert delivery.payload["attachments"][0]["sha256"] == artifact["sha256"]

    def test_attachment_error_fails_delivery_immediately(self, outbox):
        with outbox() as db:
            destination = make_destination(provider_key="webhook", config={"include_attachments": True})
            task, run = self._setup(db, destination)
            [delivery] = service.create_deliveries_for_run(db, task=task, run=run, attachment_error="capture failed")
        assert (delivery.status, delivery.error_summary) == ("failed", "capture failed")

    def test_oversized_event_fails_delivery(self, outbox):
        with outbox() as db:
            destination = make_destination(provider_key="webhook", config={"auth_mode": "none"})
            task, run = self._setup(db, destination)
            run.output_files = [{"file_id": f"f{index}", "filename": "x" * 6000} for index in range(50)]
            [delivery] = service.create_deliveries_for_run(db, task=task, run=run)
        assert delivery.status == "failed" and "256 KiB" in delivery.error_summary
        assert delivery.request_body is None

    def test_teams_delivery_stores_card(self, outbox):
        with outbox() as db:
            task, run = self._setup(db, make_destination())
            [delivery] = service.create_deliveries_for_run(db, task=task, run=run)
            db.commit()
            dto = service.delivery_dto(delivery)
        assert delivery.payload["type"] == "message"
        assert dto["provider_key"] == "teams_workflow" and dto["attempts"] == []


def test_delivery_expiry_respects_file_retention(monkeypatch):
    monkeypatch.setenv("TMP_PERSISTENT_TTL_DAYS", "1")
    remaining = service._delivery_expiry() - utcnow_naive()
    assert timedelta(hours=22, minutes=59) < remaining <= timedelta(hours=23)


# --------------------------------------------------------------------------- manual retry


class TestRequestRetry:
    def _delivery(self, db, **fields):
        delivery = OutputDelivery(run_id=1, binding_id=1, **fields)
        db.add(delivery)
        db.commit()
        return delivery

    def test_requeues_failed_delivery_with_new_generation(self, outbox):
        with outbox() as db:
            delivery = self._delivery(db, status="failed", error_summary="boom", next_attempt_at=utcnow_naive())
            service.request_retry(db, delivery)
        assert (delivery.status, delivery.dispatch_generation, delivery.error_summary) == ("pending", 1, None)

    @pytest.mark.parametrize("fields, message", [
        ({"status": "accepted"}, "Only failed"),
        ({"status": "unknown", "expires_at": datetime(2020, 1, 1)}, "expired"),
    ])
    def test_rejects_non_retryable_deliveries(self, outbox, fields, message):
        with outbox() as db:
            delivery = self._delivery(db, **fields)
            with pytest.raises(ValueError, match=message):
                service.request_retry(db, delivery)


def test_retry_delay_backs_off_with_jitter_and_cap():
    assert 22.5 <= service._retry_delay(1) <= 37.5
    assert 90 <= service._retry_delay(3) <= 150
    assert service._retry_delay(20) <= 4500


# --------------------------------------------------------------------------- connection test


class TestDestinationConnectionTest:
    @pytest.mark.asyncio
    async def test_teams_sends_test_card(self, outbox, monkeypatch):
        provider = FakeProvider()
        monkeypatch.setattr(service, "get_output_provider", lambda key: provider)
        destination = make_destination()
        assert await service.test_destination(destination) == {"http_status": 202}
        secret, payload, _ = provider.calls[0]
        assert secret == TEAMS_URL and "connection test" in str(payload)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("attachments", [False, True])
    async def test_webhook_sends_signed_test_event_and_cleans_up(self, outbox, monkeypatch, attachments):
        seen = {}

        def inspect(secret, payload, options):
            seen.update(options)
            if options["body_path"]:
                assert os.path.isfile(options["body_path"])

        provider = FakeProvider(on_send=inspect)
        monkeypatch.setattr(service, "get_webhook_provider", lambda: provider)
        destination = make_destination(provider_key="webhook", config={"include_attachments": attachments},
                                       credentials=HMAC_CREDENTIALS, content_mode="link_only")
        await service.test_destination(destination)

        _, payload, _ = provider.calls[0]
        assert payload["event_type"] == "destination.test" and payload["content"]["text"] is None
        assert seen["credentials"] == HMAC_CREDENTIALS and seen["attempt_number"] == 1
        if attachments:
            assert seen["body"] is None and seen["content_type"].startswith("multipart/form-data")
            assert payload["attachments"][0]["filename"] == "prueba.txt"
        else:
            assert seen["body"] and seen["body_path"] is None
        assert [path for path in outbox.spool.rglob("*") if path.is_file()] == []


# --------------------------------------------------------------------------- dispatch


class TestProcessDelivery:
    def _delivery(self, outbox, *, provider_key="teams_workflow", destination_fields=None, **fields):
        with outbox() as db:
            destination = make_destination(provider_key=provider_key, **(destination_fields or {}))
            db.add_all([make_task(), make_run(), destination])
            _bind(db, destination, binding_id=1)
            snapshot = {"provider_key": provider_key, "name": destination.name}
            if provider_key == "webhook":
                snapshot.update({"auth_mode": "hmac_sha256", "content_type": "application/json"})
            delivery = OutputDelivery(
                run_id=1, binding_id=1, destination_id=destination.id, payload={"event_id": "evt-1"},
                destination_snapshot={**snapshot, **fields.pop("snapshot", {})}, **fields,
            )
            db.add(delivery)
            db.commit()
            return delivery.id

    def _load(self, outbox, delivery_id):
        with outbox() as db:
            delivery = db.get(OutputDelivery, delivery_id)
            return delivery, list(delivery.attempts)

    def _provider(self, monkeypatch, provider):
        monkeypatch.setattr(service, "get_output_provider", lambda key: provider)
        monkeypatch.setattr(service, "get_webhook_provider", lambda: provider)
        return provider

    @pytest.mark.asyncio
    async def test_accepted_teams_delivery_records_receipt(self, outbox, monkeypatch):
        provider = self._provider(monkeypatch, FakeProvider({"http_status": 202}))
        delivery_id = self._delivery(outbox)
        await service.process_delivery(delivery_id, 0)
        delivery, attempts = self._load(outbox, delivery_id)
        assert (delivery.status, delivery.receipt, delivery.attempt_count) == ("accepted", {"http_status": 202}, 1)
        assert [(item.status, item.http_status) for item in attempts] == [("accepted", 202)]
        assert provider.calls[0][0] == TEAMS_URL and provider.calls[0][2] == {}

    @pytest.mark.asyncio
    async def test_webhook_delivery_sends_inline_body_with_public_config_only(self, outbox, monkeypatch):
        provider = self._provider(monkeypatch, FakeProvider())
        delivery_id = self._delivery(outbox, provider_key="webhook", request_body=b"{}",
                                     destination_fields={"credentials": HMAC_CREDENTIALS},
                                     snapshot={"include_attachments": False, "name": "ignored"})
        await service.process_delivery(delivery_id, 0)
        _, _, options = provider.calls[0]
        assert options["body"] == b"{}" and options["body_path"] is None
        assert options["config"] == {"auth_mode": "hmac_sha256", "include_attachments": False}
        assert options["credentials"] == HMAC_CREDENTIALS and options["event_id"] == "evt-1"

    @pytest.mark.asyncio
    async def test_webhook_delivery_streams_verified_spooled_body(self, outbox, monkeypatch):
        provider = self._provider(monkeypatch, FakeProvider())
        body = outbox.spool / "deliveries/evt.multipart"
        body.parent.mkdir(parents=True)
        body.write_bytes(b"multipart-body")
        delivery_id = self._delivery(outbox, provider_key="webhook", request_body_path="deliveries/evt.multipart",
                                     request_body_size=14, request_body_sha256=hashlib.sha256(b"multipart-body").hexdigest(),
                                     snapshot={"include_attachments": True})
        await service.process_delivery(delivery_id, 0)
        _, _, options = provider.calls[0]
        assert options["body"] is None and options["body_path"] == str(body)
        delivery, _ = self._load(outbox, delivery_id)
        assert delivery.status == "accepted"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("content, size, digest, message", [
        (None, 14, "x", "missing or incomplete"),
        (b"multipart-body", 99, "x", "missing or incomplete"),
        (b"multipart-body", 14, "0" * 64, "integrity"),
    ])
    async def test_webhook_spooled_body_problems_fail_permanently(self, outbox, monkeypatch, content, size, digest, message):
        provider = self._provider(monkeypatch, FakeProvider())
        if content is not None:
            path = outbox.spool / "deliveries/evt.multipart"
            path.parent.mkdir(parents=True)
            path.write_bytes(content)
        delivery_id = self._delivery(outbox, provider_key="webhook", request_body_path="deliveries/evt.multipart",
                                     request_body_size=size, request_body_sha256=digest)
        await service.process_delivery(delivery_id, 0)
        delivery, attempts = self._load(outbox, delivery_id)
        assert delivery.status == "failed" and message in delivery.error_summary
        assert attempts[0].status == "failed" and provider.calls == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("error, attempt_count, expected", [
        (DeliveryError("maybe", kind="unknown", http_status=503), 0, "unknown"),
        (DeliveryError("slow down", kind="retryable", http_status=429, retry_after=5), 0, "retry_wait"),
        (DeliveryError("slow down", kind="retryable"), 0, "retry_wait"),
        (DeliveryError("slow down", kind="retryable"), service.MAX_ATTEMPTS - 1, "failed"),
        (DeliveryError("bad request", kind="permanent", http_status=400), 0, "failed"),
    ])
    async def test_failed_attempts_are_classified(self, outbox, monkeypatch, error, attempt_count, expected):
        self._provider(monkeypatch, FakeProvider(error))
        delivery_id = self._delivery(outbox, attempt_count=attempt_count)
        await service.process_delivery(delivery_id, 0)
        delivery, attempts = self._load(outbox, delivery_id)
        assert delivery.status == expected and attempts[-1].status == expected
        assert delivery.error_summary == str(error) and delivery.lease_until is None
        if expected == "retry_wait":
            assert delivery.next_attempt_at > utcnow_naive()
        if error.retry_after:
            assert delivery.next_attempt_at - utcnow_naive() <= timedelta(seconds=5)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("fields, generation", [
        ({}, 1),
        ({"status": "accepted"}, 0),
        ({"status": "sending", "lease_until": datetime(2999, 1, 1)}, 0),
    ])
    async def test_stale_or_busy_deliveries_are_left_alone(self, outbox, monkeypatch, fields, generation):
        provider = self._provider(monkeypatch, FakeProvider())
        delivery_id = self._delivery(outbox, **fields)
        await service.process_delivery(delivery_id, generation)
        await service.process_delivery(9999, 0)
        delivery, _ = self._load(outbox, delivery_id)
        assert delivery.attempt_count == 0 and provider.calls == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("fields, destination_fields, message", [
        ({"expires_at": datetime(2020, 1, 1)}, {}, "expired"),
        ({}, {"enabled": False}, "missing or disabled"),
    ])
    async def test_expired_or_disabled_deliveries_fail(self, outbox, monkeypatch, fields, destination_fields, message):
        provider = self._provider(monkeypatch, FakeProvider())
        delivery_id = self._delivery(outbox, destination_fields=destination_fields, **fields)
        await service.process_delivery(delivery_id, 0)
        delivery, _ = self._load(outbox, delivery_id)
        assert delivery.status == "failed" and message in delivery.error_summary and provider.calls == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("provider_key, deduplicates, expected", [
        ("teams_workflow", False, "unknown"),
        ("webhook", False, "unknown"),
        ("webhook", True, "retry_wait"),
    ])
    async def test_recovered_in_flight_attempt_is_never_reposted_blindly(self, outbox, monkeypatch, provider_key, deduplicates, expected):
        provider = self._provider(monkeypatch, FakeProvider())
        delivery_id = self._delivery(outbox, provider_key=provider_key, status="sending", attempt_count=1,
                                     lease_until=datetime(2020, 1, 1), snapshot={"receiver_deduplicates": deduplicates})
        with outbox() as db:
            db.add(OutputDeliveryAttempt(delivery_id=delivery_id, attempt_number=1, status="sending"))
            db.commit()
        await service.process_delivery(delivery_id, 0)
        delivery, attempts = self._load(outbox, delivery_id)
        assert delivery.status == expected and attempts[-1].status == expected
        assert (delivery.next_attempt_at is not None) is (expected == "retry_wait")
        assert provider.calls == []

    @pytest.mark.asyncio
    async def test_late_response_does_not_overwrite_a_newer_generation(self, outbox, monkeypatch):
        delivery_id = self._delivery(outbox)

        def bump_generation(*args):
            with outbox() as db:
                db.get(OutputDelivery, delivery_id).dispatch_generation = 1
                db.commit()

        self._provider(monkeypatch, FakeProvider(on_send=bump_generation))
        await service.process_delivery(delivery_id, 0)
        delivery, attempts = self._load(outbox, delivery_id)
        assert delivery.status == "sending" and attempts[0].status == "sending"

    @pytest.mark.asyncio
    async def test_unexpected_errors_propagate(self, outbox, monkeypatch):
        self._provider(monkeypatch, FakeProvider(RuntimeError("provider crashed")))
        delivery_id = self._delivery(outbox)
        with pytest.raises(RuntimeError, match="provider crashed"):
            await service.process_delivery(delivery_id, 0)
