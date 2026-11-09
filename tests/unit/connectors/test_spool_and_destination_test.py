"""Spool containment/cleanup guarantees and the exit paths of ``test_destination``."""

from pathlib import Path

import pytest
from connectors import registry as connector_registry
from connectors.core.messages import BodyEncoding, PreparedDelivery
from services.output_channels import destination_test, spool

from .factories import make_destination

STAGE = {"file_id": "f", "filename": "a.txt", "content_type": "text/plain", "part_name": "file_1"}


class StubProvider:
    """Provider double: prepares a configurable delivery and records / fails the send."""

    def __init__(self, *, encoding=BodyEncoding.JSON, event_id="evt-1", stage=None, send_error=None):
        self.encoding, self.event_id, self.stage_name = encoding, event_id, stage
        self.send_error, self.sent = send_error, []

    def build_test_delivery(self, context, stager):
        attachments = ()
        if self.stage_name:
            attachments = (stager.stage(self.stage_name, b"data", **STAGE),)
        return PreparedDelivery(
            payload={"event_id": self.event_id}, event_id=self.event_id, body_encoding=self.encoding,
            attachments=attachments,
        )

    async def send(self, request):
        self.sent.append(request)
        if self.send_error:
            raise self.send_error
        return {"http_status": 202}


@pytest.fixture
def root_calls(outbox, monkeypatch):
    """Counts spool-root resolutions (the fixture's ``spool_root`` stub returns the temp spool)."""
    calls = []
    original = spool.spool_root

    def counting():
        calls.append(1)
        return original()

    monkeypatch.setattr(spool, "spool_root", counting)
    return calls


def _use(monkeypatch, provider):
    monkeypatch.setattr(connector_registry, "get_output_provider", lambda key: provider)


def _files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file()]


class TestStagerContainment:
    @pytest.mark.parametrize("name", ["/etc/passwd", "../escape.bin", "a/../../escape.bin"])
    def test_rejects_paths_outside_the_root(self, outbox, name):
        stager = spool.SpoolAttachmentStager(outbox.spool)
        with pytest.raises(ValueError, match="Invalid output spool reference"):
            stager.stage(name, b"x", **STAGE)
        assert _files(outbox.spool.parent) == []

    def test_rejects_symlink_escape(self, outbox, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        (outbox.spool / "link").symlink_to(outside, target_is_directory=True)
        with pytest.raises(ValueError, match="Invalid output spool reference"):
            spool.SpoolAttachmentStager(outbox.spool).stage("link/x.bin", b"x", **STAGE)
        assert list(outside.iterdir()) == []

    def test_stages_inside_the_root(self, outbox):
        stager = spool.SpoolAttachmentStager(outbox.spool)
        artifact = stager.stage("tests/a.bin", b"data", **STAGE)
        assert artifact["object_key"] == "tests/a.bin" and artifact["size_bytes"] == 4
        stager.cleanup()
        assert _files(outbox.spool) == []

    def test_path_is_registered_before_writing(self, outbox, monkeypatch):
        def partial_write(self, data):
            self.open("wb").write(data[:1])
            raise OSError("disk full")

        monkeypatch.setattr(Path, "write_bytes", partial_write)
        stager = spool.SpoolAttachmentStager(outbox.spool)
        with pytest.raises(OSError):
            stager.stage("tests/a.bin", b"data", **STAGE)
        assert len(_files(outbox.spool)) == 1
        stager.cleanup()
        assert _files(outbox.spool) == []

    def test_root_factory_is_not_called_until_a_file_is_staged(self):
        calls = []

        def factory():
            calls.append(1)
            return Path("/nonexistent-root")

        stager = spool.SpoolAttachmentStager(factory)
        stager.cleanup()
        assert calls == []


class TestDestinationTestExitPaths:
    @pytest.mark.asyncio
    async def test_json_test_does_not_touch_the_spool(self, root_calls, monkeypatch):
        provider = StubProvider()
        _use(monkeypatch, provider)
        assert await destination_test.test_destination(make_destination()) == {"http_status": 202}
        assert root_calls == []

    @pytest.mark.asyncio
    async def test_real_teams_connection_test_does_not_touch_the_spool(self, root_calls, monkeypatch):
        real = connector_registry.get_output_provider("teams_workflow")

        class Proxy:
            def __getattr__(self, name):
                return getattr(real, name)

            async def send(self, request):
                return {"http_status": 202}

        monkeypatch.setattr(connector_registry, "get_output_provider", lambda key: Proxy())
        await destination_test.test_destination(make_destination())
        assert root_calls == []

    @pytest.mark.asyncio
    async def test_staging_resolves_the_root(self, root_calls, outbox, monkeypatch):
        _use(monkeypatch, StubProvider(stage="tests/a.bin"))
        await destination_test.test_destination(make_destination())
        assert root_calls and _files(outbox.spool) == []

    @pytest.mark.asyncio
    async def test_multipart_requires_an_event_id(self, outbox, monkeypatch):
        _use(monkeypatch, StubProvider(encoding=BodyEncoding.MULTIPART, event_id=None, stage="tests/a.bin"))
        with pytest.raises(ValueError, match="multipart deliveries require an event_id"):
            await destination_test.test_destination(make_destination())
        assert _files(outbox.spool) == []

    @pytest.mark.asyncio
    async def test_staged_files_are_removed_when_the_provider_fails_while_building(self, outbox, monkeypatch):
        provider = StubProvider(stage="tests/a.bin")
        original = provider.build_test_delivery

        def build_then_fail(context, stager):
            original(context, stager)
            raise RuntimeError("boom")

        provider.build_test_delivery = build_then_fail
        _use(monkeypatch, provider)
        with pytest.raises(RuntimeError, match="boom"):
            await destination_test.test_destination(make_destination())
        assert _files(outbox.spool) == []

    @pytest.mark.asyncio
    async def test_staged_files_are_removed_when_json_body_fails(self, outbox, monkeypatch):
        _use(monkeypatch, StubProvider(stage="tests/a.bin"))

        def fail(payload):
            raise ValueError("too large")

        monkeypatch.setattr(spool, "json_body", fail)
        with pytest.raises(ValueError, match="too large"):
            await destination_test.test_destination(make_destination())
        assert _files(outbox.spool) == []

    @pytest.mark.asyncio
    async def test_multipart_file_is_removed_when_writing_fails(self, outbox, monkeypatch):
        _use(monkeypatch, StubProvider(encoding=BodyEncoding.MULTIPART, stage="tests/a.bin"))

        def write_then_fail(path, payload, attachments):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"partial")
            raise ValueError("integrity")

        monkeypatch.setattr(spool, "write_multipart", write_then_fail)
        with pytest.raises(ValueError, match="integrity"):
            await destination_test.test_destination(make_destination())
        assert _files(outbox.spool) == []

    @pytest.mark.asyncio
    async def test_multipart_and_staged_files_are_removed_when_send_fails(self, outbox, monkeypatch):
        provider = StubProvider(encoding=BodyEncoding.MULTIPART, stage="tests/a.bin", send_error=RuntimeError("down"))
        _use(monkeypatch, provider)
        with pytest.raises(RuntimeError, match="down"):
            await destination_test.test_destination(make_destination())
        assert provider.sent and provider.sent[0].body_path
        assert _files(outbox.spool) == []

    @pytest.mark.asyncio
    async def test_cleanup_failure_never_masks_the_send_error(self, outbox, monkeypatch):
        provider = StubProvider(encoding=BodyEncoding.MULTIPART, stage="tests/a.bin", send_error=RuntimeError("down"))
        _use(monkeypatch, provider)
        attempted = []

        def failing_unlink(self, missing_ok=False):
            attempted.append(self.name)
            raise PermissionError("busy")

        monkeypatch.setattr(Path, "unlink", failing_unlink)
        with pytest.raises(RuntimeError, match="down"):
            await destination_test.test_destination(make_destination())
        # Both the multipart body and the staged file were attempted despite the first failure.
        assert len(attempted) == 2

    @pytest.mark.asyncio
    async def test_cleanup_failure_does_not_turn_a_successful_test_into_an_error(self, outbox, monkeypatch):
        _use(monkeypatch, StubProvider(encoding=BodyEncoding.MULTIPART, stage="tests/a.bin"))
        monkeypatch.setattr(Path, "unlink", lambda self, missing_ok=False: (_ for _ in ()).throw(OSError("busy")))
        assert await destination_test.test_destination(make_destination()) == {"http_status": 202}
