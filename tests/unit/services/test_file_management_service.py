import pytest

from services.file_management_service import FileReference


def test_document_placeholder_is_ready_but_not_extractable():
    file_ref = FileReference(
        file_id="file-1",
        filename="brief.docx",
        file_type="document",
        content="Document file: brief.docx (Document processing not implemented)",
        file_size_bytes=128,
    )

    assert file_ref.processing_status == "ready"
    assert file_ref.has_extractable_content is False
    assert file_ref.content_preview is None


def test_processing_errors_are_not_ready():
    file_ref = FileReference(
        file_id="file-1",
        filename="broken.pdf",
        file_type="pdf",
        content="Error processing file: invalid PDF",
        file_size_bytes=128,
    )

    assert file_ref.processing_status == "error"


def _minimal_docx(text: str) -> bytes:
    """Build a minimal .docx in memory (docx2txt only reads word/document.xml)."""
    import io
    import zipfile

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", document_xml)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_docx_text_is_extracted(tmp_path):
    """Regression: .docx attachments reached the agent as a placeholder, not their text."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from services.file_management_service import FileManagementService

    upload = MagicMock()
    upload.filename = "informe.docx"
    upload.read = AsyncMock(return_value=_minimal_docx("Resumen trimestral de ventas"))

    with patch("utils.config.get_app_config", return_value={"TMP_BASE_FOLDER": str(tmp_path)}):
        fms = FileManagementService()
    file_type = fms._get_file_type(upload.filename)
    content, _, _ = await fms._process_file_content(upload, file_type)

    assert file_type == "document"
    assert "Resumen trimestral de ventas" in content


def _fms(tmp_path):
    from unittest.mock import patch
    from services.file_management_service import FileManagementService

    with patch("utils.config.get_app_config", return_value={"TMP_BASE_FOLDER": str(tmp_path / "tmp")}):
        return FileManagementService()


@pytest.mark.asyncio
async def test_save_file_rejects_dotdot_filename(tmp_path):
    """Regression (Sonar pythonsecurity:S2083): a filename of '..' escaped the target dir."""
    fms = _fms(tmp_path)
    source = tmp_path / "upload.bin"
    source.write_bytes(b"payload")
    file_ref = FileReference(file_id="f1", filename="..", file_type="text", content="x")

    await fms._save_file_to_disk("session", "f1", file_ref, original_file_path=str(source), conversation_id=7)

    assert file_ref.file_path is None
    assert not (tmp_path / "tmp" / "conversations" / "upload.bin").exists()


@pytest.mark.asyncio
async def test_save_file_keeps_normal_filename(tmp_path):
    fms = _fms(tmp_path)
    source = tmp_path / "upload.bin"
    source.write_bytes(b"payload")
    file_ref = FileReference(file_id="f1", filename="../report.xlsx", file_type="text", content="x")

    await fms._save_file_to_disk("session", "f1", file_ref, original_file_path=str(source), conversation_id=7)

    assert file_ref.file_path == "conversations/7/.._report.xlsx"
    assert (tmp_path / "tmp" / "conversations" / "7" / ".._report.xlsx").read_bytes() == b"payload"


@pytest.mark.asyncio
async def test_remove_file_does_not_delete_outside_tmp_base(tmp_path):
    """Regression (Sonar pythonsecurity:S2083): a tampered sidecar file_path deleted arbitrary files."""
    import json

    fms = _fms(tmp_path)
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me")
    session_dir = tmp_path / "tmp" / "persistent" / "session"
    session_dir.mkdir(parents=True)
    (session_dir / "f1.json").write_text(json.dumps({"file_path": "../victim.txt"}))

    await fms._remove_file_from_disk("session", "f1")

    assert victim.exists()


@pytest.mark.asyncio
async def test_remove_file_rejects_traversal_in_session_key(tmp_path):
    fms = _fms(tmp_path)
    victim = tmp_path / "tmp" / "f1.json"
    victim.write_text("{}")

    await fms._remove_file_from_disk("../", "f1")

    assert victim.exists()


def test_load_session_files_does_not_probe_outside_storage(tmp_path):
    """Regression (Sonar pythonsecurity:S6549): a crafted session key must not
    reveal whether arbitrary directories exist."""
    from unittest.mock import patch

    fms = _fms(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "f1.json").write_text('{"filename": "secret.txt", "file_type": "text"}')
    (outside / "f1.content").write_text("x")

    with patch("services.file_management_service.os.path.isdir", wraps=__import__("os").path.isdir) as isdir:
        fms._load_session_files("../../outside")

    assert "../../outside" not in fms._files
    assert not any(str(outside) in str(call.args[0]) for call in isdir.call_args_list)
